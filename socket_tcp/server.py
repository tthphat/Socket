import socket
import os
import threading
import time

HOST = socket.gethostbyname(socket.gethostname()) # Lấy IP của máy chủ
PORT = 65432
FORMAT = "utf8"
CHUNK_SIZE = 1024

def read_file(file_name): # Hàm đọc file và trả về nội dung của file chứa danh sách các tên file có thể tải
    sending = ""
    try:
        with open(file_name, "r") as f:
            for line in f:
                if line.strip():
                    sending += line.strip() + '\n'
    except FileNotFoundError:
        print(f"File not found: {file_name}")
    return sending

def send_chunk(client_socket, file_path, chunk_index, start, end): # Hàm gửi một chunk dữ liệu từ offset start đến end
    """Gửi một chunk dữ liệu từ start đến end."""
    try:
        with open(file_path, "rb") as file:
            file.seek(start)
            remaining = end - start + 1

            client_socket.sendall("DATA_START".encode(FORMAT))
            ack = client_socket.recv(1024).decode(FORMAT)
            if ack != "READY_FOR_DATA":
                raise Exception("Client không sẵn sàng nhận dữ liệu.")

            while remaining > 0:
                data = file.read(min(CHUNK_SIZE, remaining))
                if not data:
                    break
                client_socket.sendall(data)
                remaining -= len(data)

                ack = client_socket.recv(1024).decode(FORMAT)
                if ack != "DATA_ACK":
                    raise Exception("Không nhận được ACK cho dữ liệu.")

            client_socket.sendall("DATA_END".encode(FORMAT))
    except Exception as e:
        print(f"Lỗi khi gửi chunk {chunk_index}: {e}")

def handle_chunk_connection(client_socket): 
    """Xử lý yêu cầu tải chunk từ client."""
    try:
        # Gửi tín hiệu sẵn sàng
        client_socket.sendall("READY".encode(FORMAT))
        # Nhận yêu cầu chunk
        chunk_request = client_socket.recv(1024).decode(FORMAT)

        if not chunk_request.startswith("CHUNK_REQUEST"):
            raise Exception("Yêu cầu không hợp lệ.")

        # Tách thông tin yêu cầu
        _, file_name, chunk_index, start, end = chunk_request.split(":")
        chunk_index, start, end = int(chunk_index), int(start), int(end)

        # Gửi chunk dữ liệu
        send_chunk(client_socket, file_name, chunk_index, start, end)
    except Exception as e:
        print(f"Lỗi khi xử lý chunk: {e}")
    finally:
        client_socket.close()

def handle_client(client_socket, client_address):
    """Xử lý kết nối từ client."""
    try:      
        client_type = client_socket.recv(1024).decode(FORMAT)


        if client_type == "CLIENT":
            print("--------------------------------------------------------------------------------------------------------------\n")
            print(f"Client {client_address} đã kết nối.\n")
            print("--------------------------------------------------------------------------------------------------------------\n")

            client_socket.sendall(read_file("files.txt").encode(FORMAT))

            while True:
                # Nhận yêu cầu tải file từ client
                file_request = client_socket.recv(1024).decode(FORMAT)

                if file_request == "CANCEL":
                    print(f"Client {client_address} đã hủy yêu cầu tải file.")
                    continue

                if file_request == "QUIT":
                    break
                
                print("--------------------------------------------------------------------------------------------------------------\n")
                print(f"Client {client_address} yêu cầu tải file: {file_request}")

                if os.path.exists(file_request):
                    client_socket.sendall("OK".encode(FORMAT))

                    # Gửi kích thước file
                    print(f"Đang gửi file {file_request}...")
                    file_size = os.path.getsize(file_request)
                    client_socket.sendall(str(file_size).encode(FORMAT))
                    file_size_response = client_socket.recv(1024).decode(FORMAT)

                    if file_size_response == "INVALID_FILE_SIZE":
                        while file_size_response == "INVALID_FILE_SIZE":
                            file_size = os.path.getsize(file_request)
                            client_socket.sendall(str(file_size).encode(FORMAT))
                            file_size_response = client_socket.recv(1024).decode(FORMAT)


                    done_file = client_socket.recv(1024).decode(FORMAT)# Nhận tín hiệu tải xuống thành công từ client
                    if done_file == "DONE": 
                        print(f"Đã gửi file {file_request} cho client {client_address} thành công.\n")
                        print("--------------------------------------------------------------------------------------------------------------\n")
                    else:
                        print(f"Không thể gửi file {file_request} cho client {client_address}.\n")
                        print("--------------------------------------------------------------------------------------------------------------\n")
                else:
                    client_socket.sendall("NOT_FOUND".encode(FORMAT)) # Gửi thông báo không tìm thấy file
                    print(f"Không tìm thấy file {file_request}.\n")
                    print("--------------------------------------------------------------------------------------------------------------\n")       
        elif client_type == "CHUNK":
            handle_chunk_connection(client_socket)
            time.sleep(0.01)
        else:
            print(f"Loại client không hợp lệ: {client_type}")

    except ConnectionResetError:
        pass
    except Exception as e:
        print(f"Lỗi khi xử lý client {client_address}: {e}")
    finally:
        client_socket.close()

        if client_type == "CLIENT":
            print(f"Client {client_address} đã ngắt kết nối.\n")

def run_server(): # Hàm chạy server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind((HOST, PORT))
        server.listen()
        print(f"\nServer đang chạy với IP: {HOST}  ... PORT: {PORT}\n")
        print("--------------------------------------------------------------------------------------------------------------\n")
       
        while True:
            conn, addr = server.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.start()

def main():
    try:
        run_server()
    except KeyboardInterrupt:
        print(f"Server ngừng hoạt động!")
    except Exception as E:
        print(f"Error: {E}")

if __name__ == "__main__":
    main()

