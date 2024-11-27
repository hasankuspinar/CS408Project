import os
import socket
import threading
from tkinter import Tk, Label, Button, Listbox, Scrollbar, filedialog, Entry, END

class Server:
    def __init__(self):
        self.server_socket = None
        self.clients = {}
        self.file_directory = None
        self.file_list = []

    def start_server(self, port):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.bind(("", port))
            self.server_socket.listen(5)
            self.log_message(f"Server started on port {port}. Waiting for connections...")
            threading.Thread(target=self.accept_clients).start()
        except Exception as e:
            self.log_message(f"Error starting server: {e}")

    def accept_clients(self):
        while True:
            try:
                client_socket, client_address = self.server_socket.accept()
                threading.Thread(target=self.handle_client, args=(client_socket,)).start()
            except Exception as e:
                self.log_message(f"Error accepting clients: {e}")
                break

    def handle_client(self, client_socket):
        try:
            client_name = client_socket.recv(1024).decode()
            if client_name in self.clients:
                client_socket.send("ERROR: Username already connected.".encode())
                client_socket.close()
                return

            self.clients[client_name] = client_socket
            self.log_message(f"Client connected: {client_name}")
            client_socket.send("CONNECTED".encode())
            while True:
                command = client_socket.recv(1024).decode()
                if command.startswith("UPLOAD"):
                    self.handle_upload(client_name, client_socket, command)
                elif command.startswith("LIST"):
                    self.handle_list(client_socket)
                elif command.startswith("DELETE"):
                    self.handle_delete(client_name, client_socket, command)
                elif command.startswith("DOWNLOAD"):
                    self.handle_download(client_socket, command)
                elif command == "DISCONNECT":
                    self.handle_disconnect(client_name)
                    break
        except Exception as e:
            self.log_message(f"Error with client: {e}")

    def handle_upload(self, client_name, client_socket, command):
        filename = command.split(" ")[1]
        full_filename = f"{client_name}_{filename}"
        filepath = os.path.join(self.file_directory, full_filename)

        # Check if the file already exists
        if os.path.exists(filepath):
            self.log_message(f"File {filename} by {client_name} already exists. Overwriting.")

        # Write the file data
        with open(filepath, "wb") as f:
            while True:
                data = client_socket.recv(4096)
                if data == b"EOF":
                    break
                f.write(data)

        # Update the file list
        self.file_list = [(f, o) for f, o in self.file_list if not (f == filename and o == client_name)]
        self.file_list.append((filename, client_name))
        self.update_file_list()  # Persist the updated file list

        self.log_message(f"{client_name} uploaded {filename}.")
        client_socket.send(f"File {filename} uploaded successfully.".encode())

    def handle_list(self, client_socket):
        try:
            # Load the file list from the persistent file
            file_list_path = os.path.join(self.file_directory, "file_list.txt")
            
            # Check if the file list exists
            if not os.path.exists(file_list_path):
                client_socket.send("No files available.".encode())
                self.log_message("File list requested: No files available.")
                return

            # Read and send the file list to the client
            with open(file_list_path, "r") as f:
                file_list = f.read().strip()

            if file_list:
                client_socket.send(file_list.encode())
                self.log_message("File list sent to client.")
            else:
                client_socket.send("No files available.".encode())
                self.log_message("File list requested: No files available.")
        except Exception as e:
            error_message = f"Error handling file list: {e}"
            self.log_message(error_message)
            client_socket.send(error_message.encode())

    def update_file_list(self):
        file_list_path = os.path.join(self.file_directory, "file_list.txt")
        with open(file_list_path, "w") as f:
            for filename, owner in self.file_list:
                f.write(f"{filename},{owner}\n")

    def load_file_list(self):
        file_list_path = os.path.join(self.file_directory, "file_list.txt")
        if os.path.exists(file_list_path):
            with open(file_list_path, "r") as f:
                self.file_list = [tuple(line.strip().split(",")) for line in f]
        else:
            self.file_list = []


    def handle_delete(self, client_name, client_socket, command):
        filename = command.split(" ")[1]
        full_filename = f"{client_name}_{filename}"
        filepath = os.path.join(self.file_directory, full_filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            self.file_list = [(f, o) for f, o in self.file_list if not (f == filename and o == client_name)]
            self.update_file_list()  # Update the persistent file list
            self.log_message(f"{client_name} deleted {filename}.")
            client_socket.send(f"File {filename} deleted successfully.".encode())
        else:
            client_socket.send(f"ERROR: File {filename} does not exist.".encode())

    def handle_download(self, client_socket, command):
        filename, owner = command.split(" ")[1:]
        full_filename = f"{owner}_{filename}"
        filepath = os.path.join(self.file_directory, full_filename)
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                while chunk := f.read(4096):
                    client_socket.send(chunk)
            client_socket.send(b"EOF")
            self.log_message(f"File {filename} by {owner} downloaded.")
        else:
            client_socket.send(f"ERROR: File {filename} by {owner} does not exist.".encode())

    def handle_disconnect(self, client_name):
        if client_name in self.clients:
            self.clients[client_name].close()
            del self.clients[client_name]
            self.log_message(f"Client {client_name} disconnected.")

    def log_message(self, message):
        self.log_listbox.insert(END, message)

    def setup_gui(self):
        self.root = Tk()
        self.root.title("Server")
        Label(self.root, text="Port:").pack()
        self.port_entry = Entry(self.root)
        self.port_entry.pack()
        Button(self.root, text="Start Server", command=self.start_server_gui).pack()
        Button(self.root, text="Select Directory", command=self.select_directory).pack()
        self.log_listbox = Listbox(self.root)
        self.log_listbox.pack(fill="both", expand=True)
        Scrollbar(self.root, command=self.log_listbox.yview).pack(side="right", fill="y")
        self.root.mainloop()

    def start_server_gui(self):
        if not self.file_directory:
            self.log_message("Error: File directory must be selected before starting the server.")
            return
        try:
            port = int(self.port_entry.get())
            self.start_server(port)
        except ValueError:
            self.log_message("Error: Please enter a valid port number.")


    def select_directory(self):
        self.file_directory = filedialog.askdirectory()
        self.log_message(f"File directory set to: {self.file_directory}")
        self.load_file_list()  


if __name__ == "__main__":
    server = Server()
    server.setup_gui()
