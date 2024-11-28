import os
import socket
from tkinter import Tk, Label, Button, Listbox, Scrollbar, filedialog, Entry, END, messagebox
from tkinter import simpledialog
class Client:
    def __init__(self):
        self.client_socket = None
        self.server_ip = None
        self.server_port = None
        self.username = None
        self.download_directory = None

    def connect_to_server(self, ip, port, username):
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Close any existing socket
                if self.client_socket:
                    try:
                        self.client_socket.close()
                        self.client_socket = None
                    except:
                        pass
                    self.client_socket = None  # Reset to None

                # Create a new socket
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                
                # Set timeout for connection
                self.client_socket.settimeout(10)  # 10 seconds timeout
                
                # Connect
                self.client_socket.connect((ip, port))
                
                # Set longer timeout for operations
                self.client_socket.settimeout(60)  # 60 seconds timeout
                
                # Send username
                self.client_socket.send(username.encode())
                
                # Receive response
                response = self.client_socket.recv(1024).decode()
                
                if response == "CONNECTED":
                    self.log_message(f"Connected to server as {username}.")
                    self.username = username
                    self.server_ip = ip
                    self.server_port = port
                    return True
                elif response.startswith("ERROR"):
                    self.log_message(response)
                    self.client_socket.close()
                    self.client_socket = None  # Reset to None
                    return False
                else:
                    self.log_message(f"Unexpected response from server: {response}")
                    self.client_socket.close()
                    self.client_socket = None  # Reset to None
                    return False

            except (socket.timeout, ConnectionRefusedError, OSError) as e:
                self.log_message(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt == max_attempts - 1:
                    self.client_socket = None  # Reset to None
                    return False
                import time
                time.sleep(2)
                self.client_socket = None  # Reset to None before retrying

        return False


    def disconnect(self):
        try:
            if self.client_socket:
                self.client_socket.send("DISCONNECT".encode())
                self.client_socket.close()
                self.client_socket = None
                self.log_message("Disconnected from server.")
                self.username = None  # Reset username
        except Exception as e:
            self.log_message(f"Error disconnecting: {e}")
            self.client_socket = None  # Ensure client_socket is reset
            self.username = None  # Reset username

    def upload_file(self, file_path):
        if not self.client_socket:
            self.log_message("Error: Not connected to a server.")
            return

        try:
            filename = os.path.basename(file_path)
            if not os.path.exists(file_path) or not filename.strip():
                self.log_message("Error: Invalid file path or filename.")
                return

            # Get the file size
            file_size = os.path.getsize(file_path)

            # Notify the server about the upload, including the file size
            self.log_message(f"Uploading file '{filename}'...")
            self.client_socket.send(f"UPLOAD {filename} {file_size}".encode())

            # Send the file content
            with open(file_path, "rb") as f:
                while chunk := f.read(4096):
                    try:
                        self.client_socket.sendall(chunk)
                    except socket.error as e:
                        self.log_message(f"Socket error while sending chunk: {e}")
                        return

            # Wait for server response
            try:
                response = self.client_socket.recv(1024).decode()
                self.log_message(response)
            except socket.error as e:
                self.log_message(f"Error receiving server response: {e}")

        except Exception as e:
            self.log_message(f"Unexpected error during upload: {e}")

    def request_file_list(self):
        try:
            if not self.client_socket:
                self.log_message("Not connected to a server.")
                return

            # Request the file list from the server
            self.client_socket.send("LIST".encode())
            file_list = self.client_socket.recv(4096).decode()

            # Display the file list in the log box
            if file_list.strip():
                self.log_message("Files on server:")
                # Split the file list into lines
                file_lines = file_list.strip().split('\n')
                for line in file_lines:
                    self.log_message(line)
            else:
                self.log_message("No files available on the server.")
        except Exception as e:
            self.log_message(f"Error requesting file list: {e}")



    def download_file(self, filename, owner):
        if not self.download_directory:
            messagebox.showerror("Error", "Download directory not set.")
            return
        try:
            self.client_socket.send(f"DOWNLOAD {filename} {owner}".encode())

            # Wait for server response to check if file exists or get file size
            initial_response = self.client_socket.recv(1024).decode()
            if initial_response.startswith("ERROR"):
                self.log_message(initial_response)
                return
            elif initial_response.startswith("FILESIZE"):
                parts = initial_response.split(" ")
                if len(parts) != 2:
                    self.log_message("Invalid response from server.")
                    return
                file_size = int(parts[1])
            else:
                self.log_message(f"Unexpected response from server: {initial_response}")
                return

            # Send acknowledgment to server
            self.client_socket.send("READY".encode())

            save_path = os.path.join(self.download_directory, filename)
            with open(save_path, "wb") as f:
                self.log_message(f"Downloading file '{filename}'")
                bytes_received = 0
                while bytes_received < file_size:
                    chunk_size = min(4096, file_size - bytes_received)
                    data = self.client_socket.recv(chunk_size)
                    if not data:
                        raise ConnectionError("Connection lost during download.")
                    f.write(data)
                    bytes_received += len(data)

            self.log_message(f"File '{filename}' downloaded successfully.")

        except Exception as e:
            self.log_message(f"Error downloading file: {e}")


    def delete_file(self, filename):
        try:
            self.client_socket.send(f"DELETE {filename}".encode())
            response = self.client_socket.recv(1024).decode()
            self.log_message(response)
        except Exception as e:
            self.log_message(f"Error deleting file: {e}")

    def log_message(self, message):
        self.log_listbox.insert(END, message)

    def setup_gui(self):
        self.root = Tk()
        self.root.title("Client")
        self.root.geometry("600x400")

        # Server Connection Frame
        Label(self.root, text="Server IP:").pack()
        self.server_ip_entry = Entry(self.root)
        self.server_ip_entry.pack()
        Label(self.root, text="Port:").pack()
        self.port_entry = Entry(self.root)
        self.port_entry.pack()
        Label(self.root, text="Username:").pack()
        self.username_entry = Entry(self.root)
        self.username_entry.pack()
        Button(self.root, text="Connect", command=self.connect_gui).pack()

        # File Operations Frame
        Button(self.root, text="Upload File", command=self.upload_gui).pack()
        Button(self.root, text="View Files", command=self.request_file_list).pack()
        Button(self.root, text="Download File", command=self.download_gui).pack()
        Button(self.root, text="Delete File", command=self.delete_gui).pack()
        Button(self.root, text="Disconnect", command=self.disconnect_gui).pack()

        # Log Box
        self.log_listbox = Listbox(self.root)
        self.log_listbox.pack(fill="both", expand=True)
        Scrollbar(self.root, command=self.log_listbox.yview).pack(side="right", fill="y")

        self.root.mainloop()

    def connect_gui(self):
        ip = self.server_ip_entry.get().strip()
        port = self.port_entry.get().strip()
        username = self.username_entry.get().strip()

        if self.client_socket:
            response = messagebox.askyesno("Reconnect", "You are already connected. Do you want to reconnect?")
            if response:
                self.disconnect()
                import time
                time.sleep(0.5)
            else:
                return

        # Validate IP address
        if not ip:
            self.log_message("Error! IP address cannot be empty.")
            return

        # Validate port number
        if not port:
            self.log_message("Error! Port cannot be empty.")
            return

        # Validate username
        if not username:
            self.log_message("Error! Username cannot be empty.")
            return

        # Attempt to connect
        if self.connect_to_server(ip, int(port), username):
            messagebox.showinfo("Success", f"Connected to {ip}:{port} as {username}.")
        else:
            messagebox.showerror("Error", "Failed to connect to server.")


    def upload_gui(self):
        if not self.client_socket:
            self.log_message("Not connected to a server.")
            return
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if file_path:
            self.upload_file(file_path)
        else:
            self.log_message("Upload cancelled: No filename provided.")



    def download_gui(self):
        if not self.client_socket:
            self.log_message("Not connected to a server.")
            return

        # Ask user for the filename and owner
        filename = simpledialog.askstring("Download File", "Enter the filename to download:")
        if not filename:
            self.log_message("Download canceled: No filename provided.")
            return

        owner = simpledialog.askstring("Download File", "Enter the owner's username:")
        if not owner:
            self.log_message("Download canceled: No owner provided.")
            return

        # Prompt user to select the download directory
        download_directory = filedialog.askdirectory(title="Select Download Directory")
        if not download_directory:
            self.log_message("Download canceled: No directory selected.")
            return

        # Set the download directory and proceed with the download
        self.download_directory = download_directory
        self.log_message(f"Download directory set to: {self.download_directory}")
        self.download_file(filename, owner)

    def delete_gui(self):
        if not self.client_socket:
            self.log_message("Not connected to a server.")
            return

        # Ask user for the filename to delete
        filename = simpledialog.askstring("Delete File", "Enter filename to delete:")
        if not filename:
            self.log_message("Delete canceled: No filename provided.")
            return

        self.delete_file(filename)

    def disconnect_gui(self):
        self.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    client = Client()
    client.setup_gui()
