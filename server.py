import os
import socket
import threading
from tkinter import Tk, Label, Button, Listbox, Scrollbar, filedialog, Entry, END, messagebox
import traceback

class Server:
    def __init__(self):
        self.server_socket = None
        self.clients = {}
        self.clients_lock = threading.Lock()
        self.file_directory = None
        self.file_list = []
        self.error_log = []

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
        try:
            while True:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    threading.Thread(target=self.handle_client, args=(client_socket,)).start()
                except OSError:
                    # Server socket has been closed
                    break
        except Exception as e:
            self.log_message(f"Error accepting clients: {e}")


    def handle_client(self, client_socket):
        client_name = None
        disconnection_logged = False
        client_registered = False
        try:
            client_socket.settimeout(60)  # 60 seconds timeout

            client_name = client_socket.recv(1024).decode()
            with self.clients_lock:
                if client_name in self.clients:
                    client_socket.send("ERROR: Username already connected.".encode())
                    client_socket.close()
                    return
                self.clients[client_name] = client_socket
                client_registered = True  # Mark as registered

            self.log_message(f"Client connected: {client_name}")
            client_socket.send("CONNECTED".encode())

            while True:
                try:
                    client_socket.settimeout(300)  # 5 minutes
                    command = client_socket.recv(1024).decode()

                    if not command:
                        self.log_message(f"Client {client_name} disconnected.")
                        disconnection_logged = True
                        break

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
                        disconnection_logged = True
                        # Remove client from self.clients immediately
                        with self.clients_lock:
                            if client_name in self.clients:
                                del self.clients[client_name]
                        break


                except socket.timeout:
                    self.log_message(f"Client {client_name} disconnected due to timeout.")
                    disconnection_logged = True
                    break
                except (ConnectionResetError, BrokenPipeError) as conn_error:
                    self.log_message(f"Client {client_name} disconnected unexpectedly: {conn_error}")
                    disconnection_logged = True
                    break

        except Exception as e:
            self.log_message(f"Error with client {client_name}: {e}")
        finally:
            # Ensure cleanup happens
            try:
                with self.clients_lock:
                    # Only remove if the client was registered by this handler
                    if client_registered and client_name and client_name in self.clients:
                        del self.clients[client_name]
                        if not disconnection_logged:
                            self.log_message(f"Client {client_name} disconnected.")
                client_socket.close()
            except Exception as e:
                self.log_message(f"Error during cleanup for client {client_name}: {e}")
 
    def handle_upload(self, client_name, client_socket, command):
        try:
            parts = command.split(" ")
            if len(parts) < 3:
                raise ValueError("Invalid command format. Expected 'UPLOAD filename filesize'.")

            filename = parts[1].strip()
            file_size = int(parts[2].strip())

            if not filename:
                raise ValueError("Invalid filename received.")

            if not self.file_directory:
                raise ValueError("File directory not set on the server.")

            # Full file path for saving the uploaded file
            full_filename = f"{client_name}_{filename}"
            filepath = os.path.join(self.file_directory, full_filename)

            # Ensure directory exists
            os.makedirs(self.file_directory, exist_ok=True)

            # Check if the file already exists and is owned by the client
            file_exists = any(f == filename and o == client_name for f, o in self.file_list)

            if file_exists:
                self.log_message(f"File '{filename}' by client '{client_name}' will be overwritten.")

            self.log_message(f"Receiving file: {filename} from {client_name}...")

            # Read exactly file_size bytes
            bytes_received = 0
            with open(filepath, "wb") as f:
                while bytes_received < file_size:
                    chunk_size = min(4096, file_size - bytes_received)
                    data = client_socket.recv(chunk_size)
                    if not data:
                        raise ConnectionError("Client disconnected during upload.")
                    f.write(data)
                    bytes_received += len(data)

            # Update file list
            self.file_list = [(f, o) for f, o in self.file_list if not (f == filename and o == client_name)]
            self.file_list.append((filename, client_name))
            self.update_file_list()

            # Notify the client of success
            if file_exists:
                success_msg = f"File '{filename}' was overwritten successfully."
            else:
                success_msg = f"File '{filename}' uploaded successfully."
            self.log_message(success_msg)
            client_socket.send(success_msg.encode())

        except ConnectionError as conn_err:
            self.log_message(f"Connection error during upload: {conn_err}")
            client_socket.send(f"ERROR: Connection error during upload.".encode())
        except Exception as e:
            self.log_message(f"Unexpected error during upload: {e}")
            client_socket.send(f"ERROR: {e}".encode())

    def load_file_list(self):
        try:
            file_list_path = os.path.join(self.file_directory, "file_list.txt")
            
            # Create the file if it doesn't exist
            if not os.path.exists(file_list_path):
                with open(file_list_path, "w") as f:
                    pass  # Create an empty file
            
            # Read the file list
            with open(file_list_path, "r") as f:
                lines = f.readlines()
            
            # Parse the file list, handling potential formatting issues
            self.file_list = []
            for line in lines:
                line = line.strip()
                if line:
                    try:
                        filename, owner = line.split(",")
                        self.file_list.append((filename, owner))
                    except ValueError:
                        # Log any malformed lines
                        self.log_message(f"Malformed line in file list: {line}")
            
            self.log_message(f"Loaded {len(self.file_list)} files from file list.")
        except Exception as e:
            self.log_message(f"Error loading file list: {e}")
            self.file_list = []

    def update_file_list(self):
        try:
            file_list_path = os.path.join(self.file_directory, "file_list.txt")
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_list_path), exist_ok=True)
            
            # Write the file list
            with open(file_list_path, "w") as f:
                for filename, owner in self.file_list:
                    f.write(f"{filename},{owner}\n")
            
            self.log_message(f"Updated file list with {len(self.file_list)} files.")
        except Exception as e:
            self.log_error(f"Error updating file list: {e}")

    def handle_list(self, client_socket):
        try:
            # Ensure file list is loaded
            if not self.file_list:
                self.load_file_list()
            
            # Prepare file list message
            if self.file_list:
                file_list_message = "\n".join([f"{filename} (Owner: {owner})" for filename, owner in self.file_list])
                client_socket.send(file_list_message.encode())
                self.log_message("File list sent to client.")
            else:
                client_socket.send("No files available.".encode())
                self.log_message("File list is empty.")
        
        except Exception as e:
            error_message = f"Error handling file list: {e}"
            self.log_message(error_message)
            try:
                client_socket.send(error_message.encode())
            except:
                pass

    def handle_delete(self, client_name, client_socket, command):
        try:
            parts = command.split(" ")
            if len(parts) < 2:
                raise ValueError("Invalid command format. Expected 'DELETE filename'.")
            filename = parts[1]
            full_filename = f"{client_name}_{filename}"
            filepath = os.path.join(self.file_directory, full_filename)

            if os.path.exists(filepath):
                # File exists and is owned by the client
                os.remove(filepath)
                self.file_list = [(f, o) for f, o in self.file_list if not (f == filename and o == client_name)]
                self.update_file_list()
                success_msg = f"File '{filename}' deleted successfully."
                client_socket.send(success_msg.encode())
                self.log_message(f"{client_name} deleted file '{filename}'.")
            else:
                # Check if the file exists but is owned by another client
                file_exists = False
                for f, o in self.file_list:
                    if f == filename:
                        file_exists = True
                        if o != client_name:
                            # File is owned by someone else
                            error_msg = "ERROR: You cannot delete a file you didn't upload."
                            client_socket.send(error_msg.encode())
                            self.log_message(f"{client_name} attempted to delete '{filename}' owned by '{o}'.")
                            return
                if not file_exists:
                    # File does not exist at all
                    error_msg = f"ERROR: File '{filename}' does not exist."
                    client_socket.send(error_msg.encode())
                    self.log_message(error_msg)

        except Exception as e:
            error_msg = f"Error during file deletion: {e}"
            self.log_message(error_msg)
            try:
                client_socket.send(f"ERROR: {e}".encode())
            except:
                self.log_message("Failed to send error message to client.")

    def handle_download(self, client_socket, command):
        try:
            parts = command.split(" ")
            if len(parts) < 3:
                raise ValueError("Invalid command format. Expected 'DOWNLOAD filename owner'.")
            filename, owner = parts[1], parts[2]
            full_filename = f"{owner}_{filename}"
            filepath = os.path.join(self.file_directory, full_filename)

            if not os.path.exists(filepath):
                error_msg = f"ERROR: File '{filename}' by '{owner}' does not exist."
                client_socket.send(error_msg.encode())
                self.log_message(error_msg)
                return

            # Get the file size
            file_size = os.path.getsize(filepath)
            # Send the file size to the client
            client_socket.send(f"FILESIZE {file_size}".encode())

            # Wait for acknowledgment from the client
            ack = client_socket.recv(1024).decode()
            if ack != "READY":
                self.log_message("Client not ready to receive file.")
                return

            with open(filepath, "rb") as f:
                self.log_message(f"Starting download of file '{filename}' for client.")
                while chunk := f.read(4096):
                    client_socket.sendall(chunk)

            self.log_message(f"File '{filename}' by '{owner}' downloaded successfully.")

        except Exception as e:
            error_msg = f"Error during file download: {e}"
            self.log_message(error_msg)
            try:
                client_socket.send(f"ERROR: {e}".encode())
            except:
                self.log_message("Failed to send error message to client.")

    def handle_disconnect(self, client_name):
        if client_name in self.clients:
            self.clients[client_name].close()
            del self.clients[client_name]
            self.log_message(f"Client {client_name} disconnected.")

    def log_message(self, message):
        try:
            self.log_listbox.insert(END, message)
            # Optionally, also log to a file for more persistent debugging
            with open('server_log.txt', 'a') as log_file:
                log_file.write(message + '\n')
        except Exception as e:
            print(f"Logging error: {e}")

    def log_error(self, error):
        error_trace = traceback.format_exc()
        full_error_message = f"Error: {error}\nTrace: {error_trace}"
        self.error_log.append(full_error_message)
        self.log_message(full_error_message)
        
        # Write to error log file
        try:
            with open('server_error_log.txt', 'a') as error_file:
                error_file.write(full_error_message + '\n\n')
        except:
            print("Could not write to error log file")

    def setup_gui(self):
        self.root = Tk()
        self.root.title("Server")
        self.root.geometry("600x400")

        Label(self.root, text="Port:").pack()
        self.port_entry = Entry(self.root)
        self.port_entry.pack()
        Button(self.root, text="Start Server", command=self.start_server_gui).pack()
        Button(self.root, text="Select Directory", command=self.select_directory).pack()
        Button(self.root, text="Close Server", command=self.close_server).pack()
        self.log_listbox = Listbox(self.root)
        self.log_listbox.pack(fill="both", expand=True)
        Scrollbar(self.root, command=self.log_listbox.yview).pack(side="right", fill="y")
        self.root.protocol("WM_DELETE_WINDOW", self.close_server)
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

    def close_server(self):
        try:
            self.log_message("Shutting down server...")

            # Notify all clients about server shutdown
            for client_name in list(self.clients.keys()):
                client_socket = self.clients[client_name]
                try:
                    shutdown_message = "SERVER_SHUTDOWN: The server is closing."
                    client_socket.send(shutdown_message.encode())
                    self.log_message(f"Sent shutdown notification to {client_name}")
                    client_socket.close()
                except Exception as e:
                    self.log_message(f"Error notifying client {client_name}: {e}")
                finally:
                    self.log_message(f"Disconnected client {client_name}")
                    self.clients.pop(client_name, None)  # Remove client from the list

            # Stop accepting new clients
            if self.server_socket:
                self.server_socket.close()
                self.server_socket = None

            # Exit the application
            self.root.quit()
            self.root.destroy()
            self.log_message("Server closed successfully.")
        except Exception as e:
            self.log_message(f"Error closing server: {e}")
            self.root.quit()
            self.root.destroy()

    def select_directory(self):
        selected_directory = filedialog.askdirectory()
        if not selected_directory:
            self.log_message("Directory not selected.")
            return
        self.file_directory = selected_directory
        self.log_message(f"File directory set to: {self.file_directory}")
        self.load_file_list()

    def show_errors(self):
        if not self.error_log:
            messagebox.showinfo("Errors", "No errors logged.")
            return
        
        error_window = Tk()
        error_window.title("Error Log")
        error_text = Text(error_window, height=20, width=80)
        error_text.pack()
        
        for error in self.error_log:
            error_text.insert(END, error + "\n\n")
        
        error_window.mainloop()


if __name__ == "__main__":
    server = Server()
    server.setup_gui()
