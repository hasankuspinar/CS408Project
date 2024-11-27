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
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((ip, port))
            self.client_socket.send(username.encode())
            response = self.client_socket.recv(1024).decode()
            if response == "CONNECTED":
                self.log_message(f"Connected to server as {username}.")
                self.username = username
                self.server_ip = ip
                self.server_port = port
                return True
            else:
                self.log_message(response)
                self.client_socket.close()
                return False
        except Exception as e:
            self.log_message(f"Error connecting to server: {e}")
            return False

    def disconnect(self):
        try:
            if self.client_socket:
                self.client_socket.send("DISCONNECT".encode())
                self.client_socket.close()
                self.log_message("Disconnected from server.")
        except Exception as e:
            self.log_message(f"Error disconnecting: {e}")

    def upload_file(self, file_path):
        if not self.client_socket:
            self.log_message("Not connected to a server.")
            return
        try:
            filename = os.path.basename(file_path)
            self.client_socket.send(f"UPLOAD {filename}".encode())
            with open(file_path, "rb") as f:
                while chunk := f.read(4096):
                    self.client_socket.send(chunk)
            self.client_socket.send(b"EOF")
            response = self.client_socket.recv(1024).decode()
            self.log_message(response)
        except Exception as e:
            self.log_message(f"Error uploading file: {e}")

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
                self.log_message(file_list)
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
            save_path = os.path.join(self.download_directory, filename)
            with open(save_path, "wb") as f:
                while True:
                    data = self.client_socket.recv(4096)
                    if data == b"EOF":
                        break
                    f.write(data)
            self.log_message(f"File {filename} downloaded successfully.")
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
        Button(self.root, text="Set Download Directory", command=self.set_download_directory).pack()
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
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if file_path:
            self.upload_file(file_path)

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


    def set_download_directory(self):
        self.download_directory = filedialog.askdirectory()
        if self.download_directory:
            self.log_message(f"Download directory set to: {self.download_directory}")

    def disconnect_gui(self):
        self.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    client = Client()
    client.setup_gui()
