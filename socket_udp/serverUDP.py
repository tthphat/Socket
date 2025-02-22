import socket
import os
import struct
import hashlib
import threading
import time
from queue import Queue

HOST = socket.gethostbyname(socket.gethostname())
HOST_tmp = "127.0.0.1"
PORT = 65432
FORMAT = "utf8"
CHUNK_SIZE = 1024
MAX_SEQ_NUM = 10  # Số lượng gói tin tối đa có thể gửi trước khi phải đợi ACK
ack = set()
client_queue = Queue(0)
control_events = {}  

def calculate_checksum(data):
    """Calculate checksum of a packet using SHA256."""
    sha256 = hashlib.sha256()
    sha256.update(data)
    return sha256.digest()  # Returns the 32-byte checksum

def handle_acknowledgment(seq_num):
    """Handle ACK for a received chunk."""
    if seq_num not in ack:
        ack.add(seq_num)

def read_file(file_name):
    sending = ""
    try:
        with open(file_name, "r") as f:
            for line in f:
                if line.strip():
                    sending += line.strip() + '\n'
    except FileNotFoundError:
        print(f"File không tồn tại: {file_name}")
    return sending

def send_chunk(server_socket, client_address, file_path, chunk_index, start, end, seq_num=0):
    global control_events
    try:

        control_event = control_events.get(client_address)
        if not control_event:
            control_event = threading.Event()
            control_event.set()  # Mặc định cho phép gửi
            control_events[client_address] = control_event

        with open(file_path, 'rb') as file:
            file.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                control_event.wait()

                data = file.read(min(CHUNK_SIZE, remaining))                
                if not data:
                    break
                check_sum = calculate_checksum(data)

                packet = struct.pack('I', seq_num)  # 4-byte integer for chunk ID
                packet += check_sum  # 32-byte checksum
                packet += data  # The actual data chunk

                server_socket.sendto(packet, client_address)
                remaining -= len(data)
                seq_num += 1

                time.sleep(0.001)
                # if cnt == 10:
                #     cnt = 0
                #     time.sleep(0.01)
            ##-------------------------------------##
            server_socket.sendto("EOF".encode(FORMAT), client_address)

            
    except Exception as e:
        print(f"Lỗi trong khi gửi chunk {chunk_index} to {client_address}: {e}")

def handle_client(server_socket, client_address):
    global client_queue
    global control_events
    """Handle requests from the client."""
    try:
        server_socket.sendto("ACCEPT".encode(FORMAT), client_address)
        while True:
            # Receive request from client
            file_request, addr = server_socket.recvfrom(1024)
            
            if not file_request:
                break
            
            request = file_request.decode(FORMAT)
            # print(f"Received request from {client_address}: {request}")

            # Handle LIST_FILES request
            if request == "LIST_FILES":
                file_list = read_file("files.txt")
                server_socket.sendto(file_list.encode(FORMAT), client_address)

            # Handle file download request
            elif request in os.listdir():
                print(f"Client {client_address} yêu cầu tải file: {request}")
                file_size = os.path.getsize(request)
                server_socket.sendto("OK".encode(FORMAT), client_address)
                server_socket.sendto(str(file_size).encode(FORMAT), client_address)
                ack.clear()

            # Handle chunk download request
            elif request.startswith("CHUNK_REQUEST"):
                _, file_name, chunk_index, start, end, seq_num = request.split(":")
                chunk_index, start, end, seq_num = map(int, [chunk_index, start, end, seq_num])

                if client_address in control_events:
                    control_events[client_address].clear()
                
                #print(f"Received CHUNK_REQUEST from {client_address}: Resending chunk {chunk_index}.")
                threading.Thread(
                    target=send_chunk,
                    args=(server_socket, addr, file_name, chunk_index, start, end, seq_num)
                ).start()

                # Tiếp tục cờ điều khiển sau khi khởi động luồng
                if client_address in control_events:
                    control_events[client_address].set()
            # Handle ACK
            elif request.startswith("ACK"):
                try:
                    request_parts = request.split(":")
                    if len(request_parts) == 4:
                        _, file_name, chunk_index, seq_num = request_parts
                        handle_acknowledgment(int(seq_num))
                except (ValueError, IndexError):
                    print(f"ACK Không họp lệ: {request}")

            elif (client_address != addr):
                client_queue.put(addr)
                #server_socket.sendto("ServerBusy".encode(FORMAT), addr)
                continue
            elif (request == "OFF"):
                
                print(f"Ngắt kết nối với client {client_address}")
                if client_queue.empty():
                    return
                client_address = client_queue.get()
                server_socket.sendto("ACCEPT".encode(FORMAT), client_address) 
                print(f"Kết nối với client mới {client_address}")
            else:  # File not found
                server_socket.sendto("NOT_FOUND".encode(FORMAT), client_address)

    except Exception as e:
        print(f"Lỗi khi xử lý client {client_address}: {e}")

def run_server():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server_socket:
        server_socket.bind((HOST, PORT))

        while True:
            try:
                print(f"Server đang chạy với IP: {HOST} ... PORT: {PORT}")
                socket_type, client_address = server_socket.recvfrom(1024)
                if socket_type.decode(FORMAT) == "CLIENT":
                    print(f"Client {client_address} đã kết nối.")
                    handle_client(server_socket, client_address)
                else:
                    print(f"Yêu cầu không hợp lệ từ {client_address}")
                    type = socket_type.decode(FORMAT)
                    print(f"{type}\n")

            except Exception as e:
                print(f"Lỗi tiến trình không hợp lệ từ: {e}")

def main():
    try:
        run_server()
    except KeyboardInterrupt:
        print("Server dừng!")
    except Exception as E:
        print(f"Error: {E}")

if __name__ == "__main__":
    main()
