import grpc
from concurrent.futures import ThreadPoolExecutor
from grpc_text_app.auth import upwd
import message_pb2
import message_pb2_grpc
from typing import Dict, Iterator
import queue
import threading
import logging

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# Dictionary to store active clients and their response queues
active_clients: Dict[str, queue.Queue] = {}  # Stores a message queue for each client
lock = threading.Lock()  # Ensure thread safety

class MessageService(message_pb2_grpc.MessageServiceServicer):
    def ChatStream(
        self, request_iterator: Iterator[message_pb2.MessageRequest], context: grpc.ServicerContext
    ) -> Iterator[message_pb2.MessageResponse]:
        """Handles bi-directional streaming and keeps the connection alive."""

        # Register the client and create its message queue
        first_request = next(request_iterator, None)
        if not first_request:
            return  # If there's no first request, terminate the connection

        sender_id = first_request.sender_id
        logger.info(f"Client {sender_id} connected.")

        with lock:
            if sender_id not in active_clients:
                active_clients[sender_id] = queue.Queue()  # Create a queue for each client

        try:
            while True:
                # Check if the client sent a message
                try:
                    request = next(request_iterator)
                    # Add message to recipient's queue
                    with lock:
                        recipient_queue = active_clients.get(request.receiver_id)

                    if recipient_queue:
                        if request.message != "_heartbeat_":
                            recipient_queue.put((request.sender_id, request.receiver_id, request.message))
                        else:
                            logger.debug(f"Heartbeat received from {request.sender_id}.")

                except StopIteration:
                    logger.error(f"Client {sender_id} disconnected.")
                    break  # StopIteration means the client disconnected

                # Send messages from queue immediately
                while not active_clients[sender_id].empty():
                    sender_id, receiver_id, message_text = active_clients[sender_id].get()
                    yield message_pb2.MessageResponse(
                        status=message_pb2.StatusCode.OK,
                        sender_id=sender_id,
                        receiver_id=receiver_id,
                        message=message_text
                    )

        finally:
            # Remove client when they disconnect
            with lock:
                active_clients.pop(sender_id, None)
            logger.error(f"Client {sender_id} removed from active clients.")

class AuthenticationService(message_pb2_grpc.AuthenticationServiceServicer):
    def Login(self, request: message_pb2.LoginRequest, context: grpc.ServicerContext) -> message_pb2.LoginResponse:
        """Handles client login requests."""
        logger.info(f"Login request received for {request.username}, {request.password}")
        if request.username in upwd and upwd[request.username] == request.password:
            return message_pb2.LoginResponse(status=message_pb2.StatusCode.OK)
        else:
            return message_pb2.LoginResponse(status=message_pb2.StatusCode.FAIL)

def serve() -> None:
    """Starts the gRPC server."""
    server = grpc.server(ThreadPoolExecutor(max_workers=10))
    message_pb2_grpc.add_MessageServiceServicer_to_server(MessageService(), server)
    message_pb2_grpc.add_AuthenticationServiceServicer_to_server(AuthenticationService(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    logger.info("gRPC Server is running on port 50051...")
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
