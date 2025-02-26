import click
import grpc
import message_pb2
import message_pb2_grpc
import time
import threading
import queue
from typing import Iterable
import logging

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

def combined_message_stream(sender_id: str, receiver_id: str) -> Iterable[message_pb2.MessageRequest]:
    """Generates both user messages and heartbeats using the same queue."""
    message_queue = queue.Queue()

    def user_input_stream():
        logger.info(f"Chat started! Type your messages to {receiver_id} (Type 'exit' to quit).")
        while True:
            message_text = input(f"{sender_id} -> {receiver_id}: ")  # Get message
            if message_text.lower() == "exit":
                logger.info("Exiting chat...")
                break  # Stop sending messages
            
            message_queue.put(message_pb2.MessageRequest(
                message=message_text,
                sender_id=sender_id,
                receiver_id=receiver_id
            ))
    
    def heartbeat_stream():
        while True:
            time.sleep(1)  # Send heartbeat every second
            message_queue.put(message_pb2.MessageRequest(
                message="_heartbeat_", sender_id=sender_id, receiver_id="server"))
    
    threading.Thread(target=user_input_stream, daemon=True).start()
    threading.Thread(target=heartbeat_stream, daemon=True).start()
    
    while True:
        yield message_queue.get()

def chat_with_server(sender_id: str, receiver_id: str) -> None:
    """Connects to the server and starts bi-directional communication."""
    channel = grpc.insecure_channel("localhost:50051")
    stub = message_pb2_grpc.MessageServiceStub(channel)

    # Create a combined request iterator for messages and heartbeats
    request_iterator = combined_message_stream(sender_id, receiver_id)

    # Start the chat stream
    response_iterator = stub.ChatStream(request_iterator)

    # Continuously listen for messages and print them immediately
    for response in response_iterator:
        if response.status == message_pb2.StatusCode.OK and response.receiver_id == sender_id:
            print(f"\n{response.sender_id} -> {response.receiver_id}: {response.message}")
        elif response.status == message_pb2.StatusCode.FAIL:
            logger.error(f"Error: {response.message}")

@click.command()
@click.option("--username", prompt="Enter your username", help="Your username")
@click.password_option("--password", prompt="Enter your password", help="Your password")
def main(username, password):
    channel = grpc.insecure_channel("localhost:50051")
    stub = message_pb2_grpc.AuthenticationServiceStub(channel)
    response = stub.Login(message_pb2.LoginRequest(username=username, password=password))
    if response.status == message_pb2.StatusCode.OK:
        receiver_id = input("Enter recipient ID: ").strip()
        chat_with_server(username, receiver_id)
    else:
        logger.error(f"Login failed: {response.status}")


if __name__ == "__main__":
    main()
