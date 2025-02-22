import socket
import time
import threading
import os
#from tkinter import filedialog
from tkinter import Tk, Listbox, Button, filedialog
from tqdm import tqdm

HOST = input("Nhập Host IP: ") # Nhập IP của máy chủ server
PORT = 65432    
FORMAT = "utf8"
progress = [0] * 4
lock = threading.Lock()

def read_new_files(file_name, already_downloaded): # Hàm đọc file và trả về danh sách các file mới cần tải
    try:
        with open(file_name, "r") as f:
            lines = f.readlines()
            new_files = [line.strip() for line in lines if line.strip() not in already_downloaded]
            return new_files
    except FileNotFoundError:
        print(f"File '{file_name}' không tồn tại.")
        return []
    except Exception as e:
        print(f"Có lỗi khi đọc file '{file_name}': {e}")
        return []

def write_data_into_file(chunk_paths, download_folder_path, file_name):# Hàm ghi dữ liệu (chunk) vào file
    downloaded_file = os.path.join(download_folder_path, file_name)
    with open(downloaded_file, 'wb') as f:
        for chunk_data in chunk_paths:
            if chunk_data is not None:
                f.write(chunk_data) 
    
    print("\n")
    print(f"File '{file_name}' đã được tải xuống thành công tại {downloaded_file}.\n\n")
    print("--------------------------------------------------------------------------------\n")



# Thêm Barrier để đồng bộ hóa các luồng
barrier = threading.Barrier(4)  # Đồng bộ hóa 4 luồng

def download_chunk(host, port, file_name, chunk_paths, chunk_index, start, end, progress_bars, lock):
    """Tải xuống một chunk từ server."""
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((host, port))
        client_socket.sendall("CHUNK".encode(FORMAT))
        response = client_socket.recv(1024).decode(FORMAT)

        if response != "READY":
            raise Exception("Server không sẵn sàng.")

        request = f"CHUNK_REQUEST:{file_name}:{chunk_index}:{start}:{end}"
        client_socket.sendall(request.encode(FORMAT))

        response = client_socket.recv(1024).decode(FORMAT)
        if response != "DATA_START":
            raise Exception("Không nhận được tín hiệu bắt đầu.")

        client_socket.sendall("READY_FOR_DATA".encode(FORMAT))
        chunk_data = bytearray()
        total_received = 0
        chunk_size = end - start + 1

        # Thanh tiến trình cho từng chunk
        chunk_progress = progress_bars[chunk_index]

        while True:
            data = client_socket.recv(1024)
            if data == b"DATA_END":
                break
            chunk_data.extend(data)
            with lock:
                chunk_progress.update(len(data))
            client_socket.sendall("DATA_ACK".encode(FORMAT))
            total_received += len(data)
            # Đồng bộ hóa các luồng sau mỗi lần tải xong một đoạn nhỏ
            barrier.wait()

        chunk_paths[chunk_index] = chunk_data
    except Exception as e:
        print(f"Lỗi khi tải chunk {chunk_index}: {e}")
    finally:
        client_socket.close()
        chunk_progress.close()  # Đóng thanh tiến trình sau khi hoàn tất

def download_file(client, file_name, gui_listbox):
    """Tải xuống file từ server theo từng chunk."""
    try:
        print("--------------------------------------------------------------------------------\n")
        print(f"Đang tải file '{file_name}'...")

        while True:
            file_size_str = client.recv(1024).decode(FORMAT).strip()
            if not file_size_str.isdigit() or int(file_size_str) <= 0:
                print("Kích thước file không hợp lệ, yêu cầu server gửi lại.")
                client.sendall("INVALID_FILE_SIZE".encode(FORMAT))
            else:
                file_size = int(file_size_str)
                client.sendall("VALID_FILE_SIZE".encode(FORMAT))
                break

        # Chọn thư mục để lưu file
        download_folder_path = filedialog.askdirectory(title=f"Chọn thư mục lưu file {file_name}")
        if not download_folder_path:
            print("Chưa chọn thư mục tải về. Hủy quá trình tải.\n")
            client.sendall("CANCEL".encode(FORMAT))
            return

        # Chia kích thước file thành các chunk
        num_chunks = 4
        chunk_size = file_size // num_chunks
        threads = []
        chunk_paths = [None] * num_chunks

        # Tạo thanh tiến trình cho từng chunk
        progress_bars = [
            tqdm(
                total=chunk_size if i != num_chunks - 1 else file_size - (num_chunks - 1) * chunk_size,
                desc=f"Downloading {file_name} part {i + 1}",
                unit="bytes",
                unit_scale=True,
                # dynamic_ncols=True,
                bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} {unit}",
            )
            for i in range(num_chunks)
        ]

        for i in range(num_chunks):
            start = i * chunk_size
            end = file_size - 1 if i == num_chunks - 1 else (start + chunk_size - 1)
            thread = threading.Thread(
                target=download_chunk,
                args=(HOST, PORT, file_name, chunk_paths, i, start, end, progress_bars, threading.Lock())
            )
            threads.append(thread)
            thread.start()
            time.sleep(0.7)

        for thread in threads:
            thread.join()

        # Kiểm tra xem đã nhận đủ byte của file chưa
        total_received = sum(len(chunk) for chunk in chunk_paths if chunk is not None)
        if total_received != file_size:
            raise Exception("Không nhận đủ dữ liệu.")

        # Ghi dữ liệu vào file
        write_data_into_file(chunk_paths, download_folder_path, file_name)
        client.sendall("DONE".encode(FORMAT))

        gui_listbox.insert('end', file_name)

    except Exception as e:
        print(f"Lỗi khi tải file: {e}")



def control_files_to_download(client, file_name, gui_listbox, root): # Hàm giám sát file input.txt, đảm bảo quét 5s một lần
    already_downloaded = set()  # Lưu danh sách các file đã tải
    print("Bắt đầu giám sát file input.txt. Nhấn Ctrl+C để dừng.\n\n")
    try:
        while True:
            # Đọc các file mới cần tải
            new_files = read_new_files(file_name, already_downloaded)
            if new_files:
                print(f"Các file mới cần tải: {new_files}\n")
            else:
                print("Không có File cần tải xuống!")

            for file in new_files:
                client.sendall(file.encode(FORMAT))
                response = client.recv(1024).decode(FORMAT)

                if response == "OK":
                    download_file(client, file, gui_listbox)
                    time.sleep(0.5)
                elif response == "NOT_FOUND":
                    print(f"Không thể tải file '{file}'.\n")
                already_downloaded.add(file) # Đánh dấu file đã tải

            time.sleep(5)  # Chờ 5 giây trước khi quét lại
    except KeyboardInterrupt:
        client.sendall("QUIT".encode(FORMAT))
        print("\nDừng giám sát file.")
        root.quit()  # Đóng giao diện
        return
    except Exception as e:
        print(f"Có lỗi xảy ra: {e}")



def start_gui(client):
    root = Tk()
    root.title("File đã tải xuống")

    listbox = Listbox(root, width=50, height=20)
    listbox.pack(pady=10)

    quit_button = Button(root, text="Thoát", command=lambda: root.quit())
    quit_button.pack(pady=5)

    threading.Thread(target=control_files_to_download, args=(client, "input.txt", listbox, root), daemon=True).start()

    # root.mainloop()
    try:
        root.mainloop()
    except KeyboardInterrupt:
        root.quit()

def main():
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((HOST, PORT))        
        client.sendall("CLIENT".encode(FORMAT))
        time.sleep(1)
       
        list_files = client.recv(1024).decode(FORMAT)
        print("Danh sách file từ server:")
        print(list_files)

        start_gui(client) # Bắt đầu giao diện người dùng
        # control_files_to_download(client, "input.txt")

    except Exception as e:
        print(f"Có lỗi khi kết nối đến server: {e}")
    finally:
        print("Client đã thoát.")
        
if __name__ == "__main__":
    main()
