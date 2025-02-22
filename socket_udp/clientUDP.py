import socket
import os
import time
import threading
from tkinter import filedialog
#from tkinter import Tk, Listbox, Button, filedialog
from tqdm import tqdm
import hashlib
import struct

HOST = input("Nhập HOST IP: ")
PORT = 65432
FORMAT = "utf8"
CHUNK_SIZE = 2048
MAX_RETRIES = 5
TIMEOUT = 2
WINDOW_SIZE = 5
ack_lock = threading.Lock()

def calculate_checksum(data):
    sha256 = hashlib.sha256()
    sha256.update(data)
    return sha256.digest() 

def download_chunk(server_address, filename, chunk_index, start_chunk, end_chunk, chunks_data):
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        timeout = 5.0
        client_socket.settimeout(timeout)

        request = f"CHUNK_REQUEST:{filename}:{chunk_index}:{start_chunk}:{end_chunk}:{0}".encode()
        client_socket.sendto(request, server_address)

        chunk_data = bytearray() 
        pre_seq_num = 0
        chunk_size = end_chunk - start_chunk + 1
        total_received = 0

        chunk_progress = tqdm(
            total=chunk_size,
            desc=f"Downloading {filename} part {chunk_index + 1}",
            unit="bytes",
            unit_scale=True,
            # dynamic_ncols=True,  # Tự điều chỉnh kích thước thanh
            mininterval=0.5,  # Giảm tần suất cập nhật
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} {unit}"
        )

        while True:
            try:
                packet,_ = client_socket.recvfrom(CHUNK_SIZE)

                if packet == b"EOF":
                    break

                seq_num, = struct.unpack('I', packet[:4]) 
                checksum = packet[4:36]
                data = packet[36:]

                if calculate_checksum(data) == checksum:
                    if seq_num != pre_seq_num:
                        request = f"CHUNK_REQUEST:{filename}:{chunk_index}:{total_received}:{end_chunk}:{pre_seq_num}".encode()
                        client_socket.sendto(request, server_address)
                        continue
                    
                    chunk_data.extend(data)
                    chunk_progress.update(len(data))
                    ack = f"ACK:{filename}:{chunk_index}:{seq_num}".encode()
                    
                    with ack_lock:
                        client_socket.sendto(ack, server_address)
                    pre_seq_num += 1
                    total_received += len(data)

                else:
                    request = f"CHUNK_REQUEST:{filename}:{chunk_index}:{total_received}:{pre_seq_num}".encode()
                    client_socket.sendto(request, server_address)

            except socket.timeout:
                timeout = min(5.0, timeout * 1.5)
                request = f"CHUNK_REQUEST:{filename}:{chunk_index}:{total_received}:{end_chunk}:{pre_seq_num}".encode()
                client_socket.sendto(request, server_address)

        
        if chunk_data and len(chunk_data) != 0: 
            chunks_data[chunk_index] = chunk_data

    except Exception as e:
        print(f"[ERROR] Part {chunk_index + 1}: {e}")

    finally:
        client_socket.close()
        chunk_progress.close()



def download_file(file_name, client_socket):
    """Tải file từ server."""
    try:
        print(f"Đang tải file '{file_name}'...")
        file_size, _ = client_socket.recvfrom(1024)
        file_size = int(file_size.decode(FORMAT))

        # Chọn thư mục lưu file
        download_folder_path = filedialog.askdirectory(title=f"Chọn thư mục lưu file {file_name}")
        if not download_folder_path:
            print("Không chọn thư mục, hủy tải file.\n")
            print("--------------------------------------------------------------------------------\n")

            return

        # Chia file thành các chunk
        num_chunks = 4
        chunk_size = file_size // num_chunks
        threads = []
        chunks_data = [None] * num_chunks

        for i in range(num_chunks):
            start = i * chunk_size
            end = file_size - 1 if i == num_chunks - 1 else (start + chunk_size - 1)
            thread = threading.Thread(
                target = download_chunk,
                args = ((HOST, PORT), file_name, i, start, end, chunks_data)
            )
            threads.append(thread)
            thread.start() 

        for thread in threads:
            thread.join()

          #kiểm tra xem đã nhận đủ byte của file chưa
        total_received = sum(len(chunk) for chunk in chunks_data if chunk is not None)
        if total_received != file_size:
            raise Exception("Không nhận đủ dữ liệu.")
        

        # Ghi dữ liệu vào file
        output_file_path = os.path.join(download_folder_path, file_name)
        with open(output_file_path, "wb") as f:
            for i in range(num_chunks):
                chunk = chunks_data[i]
                if chunk is not None:
                    f.write(chunk)

        client_socket.sendto("DONE".encode(FORMAT), (HOST, PORT))

        print(f"\nFile '{file_name}' đã được tải xuống thành công tại: {output_file_path}")
        print("--------------------------------------------------------------------------------\n")
    except Exception as e:
        print(f"Lỗi khi tải file: {e}")


def list_files(client_socket):
    """Gửi yêu cầu danh sách file và nhận kết quả."""
    client_socket.sendto("LIST_FILES".encode(FORMAT), (HOST, PORT))
    file_list, _ = client_socket.recvfrom(1024)
    print("Danh sách file trên server:")
    print(file_list.decode(FORMAT))


def monitor(client_socket, input_file, server_address):
    """Giám sát file input.txt và tải các file mới."""
    already_downloaded = set()
    print("Bắt đầu giám sát file input.txt. Nhấn Ctrl+C để dừng.")
    try:
        while True:
            # Đọc file input.txt
            new_files = read_new_files(input_file, already_downloaded)
            if new_files:
                print(f"Các file mới cần tải: {new_files}\n")
            else:
                print("Không có file cần tải xuống.")

            for file_name in new_files:
                client_socket.sendto(file_name.encode(FORMAT), server_address)
                response, _ = client_socket.recvfrom(1024)

                if response.decode(FORMAT) == "OK":
                    # Nhận kích thước file
                    download_file(file_name, client_socket)
                elif response.decode(FORMAT) == "NOT_FOUND":
                    print(f"File '{file_name}' không tồn tại trên server.\n")
                    print("--------------------------------------------------------------------------------\n")


                already_downloaded.add(file_name)
            time.sleep(5)  # Chờ 5 giây trước khi quét lại
    except KeyboardInterrupt:
        print("\nDừng giám sát file.")
        return
    except Exception as e:
        print(f"Lỗi khi giám sát file: {e}")


def read_new_files(file_name, already_downloaded):
    """Đọc danh sách file từ input.txt và trả về file mới chưa tải."""
    try:
        with open(file_name, "r") as f:
            lines = f.readlines()
            return [line.strip() for line in lines if line.strip() not in already_downloaded]
    except FileNotFoundError:
        print(f"File '{file_name}' không tồn tại.")
        return []


def main():
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_socket.settimeout(2)
        # Gửi tín hiệu kết nối đến server
        client_socket.sendto("CLIENT".encode(FORMAT), (HOST, PORT))
        flag = 0

        # Nhận phản hồi từ server
        while True:
            try:
                response, server_address = client_socket.recvfrom(1024)
                response = response.decode(FORMAT)
                if response == "ACCEPT":
                    print("Đã kết nối với server.")
                    list_files(client_socket)
                    monitor(client_socket, "input.txt", server_address)
                    break
                else:
                    print("Kết nối không thành công")
            except socket.timeout:
                if flag == 1:
                    continue
                flag = 1
                print("Đã có client khác kết nối vào server, đang đợi......")
    except Exception as e:
        print(f"Lỗi client: {e}")
    except KeyboardInterrupt:
        print("\nDừng chờ kết nối")
    finally:
        print("Client đã thoát.")
        client_socket.sendto("OFF".encode(FORMAT), server_address)
        client_socket.close()


if __name__ == "__main__":
    main()
