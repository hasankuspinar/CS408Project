import os
import socket
import threading
import queue
from tkinter import Tk, Label, Button, Listbox, Scrollbar, filedialog, Entry, END, messagebox
from tkinter import simpledialog

class Client:
    def __init__(self):
        self.client_socket = None
        self.server_ip = None
        self.server_port = None
        self.username = None
        self.download_directory = None
        self.listener_thread = None
        self.listening = False
        self.socket_lock = threading.Lock()  # Lock for socket operations
        self.gui_queue = queue.Queue()       # Queue for thread-safe GUI updates
        self.current_download = None         # Initialize current_download

    def connect_to_server(self, ip, port, username):
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Close any existing socket
                with self.socket_lock:
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
                        self.gui_queue.put(f"Connected to server as {username}.")
                        self.username = username
                        self.server_ip = ip
                        self.server_port = port

                        # Start the listener thread
                        self.listening = True
                        self.listener_thread = threading.Thread(target=self.listen_to_server, daemon=True)
                        self.listener_thread.start()

                        return True
                    elif response.startswith("ERROR"):
                        self.gui_queue.put(response)
                        self.client_socket.close()
                        self.client_socket = None  # Reset to None
                        return False
                    else:
                        self.gui_queue.put(f"Unexpected response from server: {response}")
                        self.client_socket.close()
                        self.client_socket = None  # Reset to None
                        return False

            except ConnectionRefusedError:
                self.gui_queue.put("Server is not open.")
                self.client_socket = None  # Reset to None
                return False
            except (socket.timeout, OSError) as e:
                self.gui_queue.put(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt == max_attempts - 1:
                    self.client_socket = None  # Reset to None
                    self.gui_queue.put("Failed to connect after multiple attempts.")
                    return False
                import time
                time.sleep(2)
                self.client_socket = None  # Reset to None before retrying

        self.gui_queue.put("Failed to connect after multiple attempts.")
        return False

    def listen_to_server(self):
        while self.listening and self.client_socket:
            try:
                message = self.client_socket.recv(4096)
                if not message:
                    self.gui_queue.put("Disconnected from server.")
                    self.disconnect()
                    break

                decoded_message = message.decode()

                # Ignore debug messages
                if decoded_message.startswith("DEBUG:"):
                    continue  # Skip debug messages

                # Handle server shutdown
                if decoded_message.startswith("SERVER_SHUTDOWN:"):
                    shutdown_msg = decoded_message.replace("SERVER_SHUTDOWN:", "").strip()
                    self.gui_queue.put(f"** Server Shutdown: {shutdown_msg} **")
                    self.disconnect()
                    break

                # Handle notifications (e.g., file downloaded)
                if decoded_message.startswith("NOTIFICATION:"):
                    notification = decoded_message.replace("NOTIFICATION:", "").strip()
                    self.gui_queue.put(f"** Notification: {notification} **")
                    continue  # Continue to next message

                # Handle file list
                if "Owner:" in decoded_message:
                    # Assume it's a file list
                    lines = decoded_message.strip().split('\n')
                    file_entries = []
                    for line in lines:
                        if "Owner:" in line:
                            # Extract filename and owner
                            try:
                                filename_part, owner_part = line.split(" (Owner: ")
                                owner = owner_part.rstrip(")")
                                filename = filename_part.strip()
                                file_entries.append(f"{filename} - {owner}")
                            except ValueError:
                                # Handle unexpected format
                                file_entries.append(f"Invalid file entry: {line}")

                    if file_entries:
                        self.gui_queue.put("File List:")
                        for entry in file_entries:
                            self.gui_queue.put(entry)
                    else:
                        self.gui_queue.put("No files available on the server.")
                    continue  # Continue to next message

                # Handle upload responses
                if decoded_message.startswith("UPLOAD_RESPONSE:"):
                    # Handle upload response
                    upload_response = decoded_message.replace("UPLOAD_RESPONSE:", "").strip()
                    self.gui_queue.put(upload_response)
                    if "overwritten" in upload_response.lower():
                        filename = self.current_download['filename'] if self.current_download else "unknown"
                        messagebox.showinfo("File Overwritten", f"The file '{filename}' has been overwritten on the server.")
                    elif "uploaded successfully" in upload_response.lower():
                        filename = self.current_download['filename'] if self.current_download else "unknown"
                        messagebox.showinfo("Upload Successful", f"The file '{filename}' has been uploaded successfully.")
                    continue  # Continue to next message

                # Handle file download initiation
                if decoded_message.startswith("FILESIZE"):
                    # Handle file download
                    parts = decoded_message.split(" ")
                    if len(parts) == 2:
                        try:
                            file_size = int(parts[1])
                            if self.current_download and self.current_download['filename'] and self.current_download['owner']:
                                self.current_download['file_size'] = file_size
                                # Send acknowledgment
                                self.client_socket.send("READY".encode())
                                # Open file for writing
                                self.current_download['file'] = open(self.current_download['save_path'], "wb")
                                self.gui_queue.put(f"Downloading file '{self.current_download['filename']}'...")
                        except ValueError:
                            self.gui_queue.put("Invalid FILESIZE value received.")
                    else:
                        self.gui_queue.put("Invalid FILESIZE response from server.")
                    continue  # Continue to next message

                # Handle other messages or file data
                if self.current_download and self.current_download['file']:
                    try:
                        # Write the incoming data to the file
                        self.current_download['file'].write(message)
                        self.current_download['bytes_received'] += len(message)
                        if self.current_download['bytes_received'] >= self.current_download['file_size']:
                            self.current_download['file'].close()
                            self.gui_queue.put(f"File '{self.current_download['filename']}' downloaded successfully.")
                            # Reset current_download
                            self.current_download = None
                    except Exception as e:
                        self.gui_queue.put(f"Error writing to file: {e}")
                        if self.current_download['file']:
                            self.current_download['file'].close()
                        self.current_download = None
                else:
                    self.gui_queue.put(decoded_message)
            except socket.timeout:
                continue  # Continue listening
            except (ConnectionResetError, OSError):
                self.gui_queue.put("Connection lost.")
                self.disconnect()
                break
            except Exception as e:
                self.gui_queue.put(f"Error receiving message: {e}")
                self.disconnect()
                break

    def process_gui_queue(self):
        try:
            while not self.gui_queue.empty():
                message = self.gui_queue.get_nowait()
                if message.startswith("** Notification:"):
                    # Show download notification as a popup
                    if "downloaded" in message.lower():
                        notification_text = message.replace("** Notification:", "").strip()
                        messagebox.showinfo("Download Notification", notification_text)
                    else:
                        self.log_listbox.insert(END, message)
                elif message.startswith("** Server Shutdown:"):
                    # Show server shutdown as a popup
                    shutdown_text = message.replace("** Server Shutdown:", "").strip()
                    messagebox.showwarning("Server Shutdown", shutdown_text)
                else:
                    self.log_listbox.insert(END, message)
                    self.log_listbox.yview_moveto(1)  # Auto-scroll to the end
        except queue.Empty:
            pass
        except Exception as e:
            messagebox.showerror("Error", f"Error processing GUI queue: {e}")
        finally:
            # Schedule the next check after 100 milliseconds
            self.root.after(100, self.process_gui_queue)

    def disconnect(self):
        try:
            self.listening = False
            with self.socket_lock:
                if self.client_socket:
                    try:
                        self.client_socket.send("DISCONNECT".encode())
                    except:
                        pass
                    self.client_socket.close()
                    self.client_socket = None
            # Close any open download files
            if self.current_download and self.current_download.get('file'):
                self.current_download['file'].close()
                self.current_download = None
            self.gui_queue.put("Disconnected from server.")
            self.username = None  # Reset username
        except Exception as e:
            self.gui_queue.put(f"Error disconnecting: {e}")
            self.client_socket = None  # Ensure client_socket is reset
            self.username = None  # Reset username

    def upload_file(self, file_path):
        if not self.client_socket:
            self.gui_queue.put("Error: Not connected to a server.")
            return

        try:
            filename = os.path.basename(file_path)
            if not os.path.exists(file_path) or not filename.strip():
                self.gui_queue.put("Error: Invalid file path or filename.")
                return

            # Get the file size
            file_size = int(os.path.getsize(file_path))

            # Notify the server about the upload, including the file size
            self.gui_queue.put(f"Uploading file '{filename}'...")
            self.client_socket.send(f"UPLOAD {filename} {file_size}".encode())

            # Track the upload as a current download for potential overwrite notifications
            self.current_download = {
                'filename': filename,
                'owner': self.username,  # Assuming uploader is the owner
                'save_path': None,       # Not applicable for uploads
                'file_size': 0,
                'bytes_received': 0,
                'file': None
            }

            # Send the file content
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(4096)
                    if not chunk:
                        break
                    self.client_socket.sendall(chunk)

            # No recv here; listener thread will handle the server response
        except Exception as e:
            self.gui_queue.put(f"Unexpected error during upload: {e}")

    def request_file_list(self):
        try:
            if not self.client_socket:
                self.gui_queue.put("Not connected to a server.")
                return

            # Request the file list from the server
            self.client_socket.send("LIST".encode())
            # Do NOT perform recv here; listener thread will handle the response
        except Exception as e:
            self.gui_queue.put(f"Error requesting file list: {e}")

    def download_file(self, filename, owner):
        if not self.download_directory:
            messagebox.showerror("Error", "Download directory not set.")
            return
        try:
            # Check if a download is already in progress
            if self.current_download and self.current_download['file']:
                self.gui_queue.put("Error: A download is already in progress.")
                messagebox.showerror("Download Error", "A download is already in progress.")
                return

            # Track the current download
            self.current_download = {
                'filename': filename,
                'owner': owner,
                'save_path': os.path.join(self.download_directory, filename),
                'file_size': 0,
                'bytes_received': 0,
                'file': None
            }

            self.client_socket.send(f"DOWNLOAD {filename} {owner}".encode())
            self.gui_queue.put(f"Initiated download for '{filename}' from '{owner}'.")
            # Listener thread will handle the rest
        except Exception as e:
            self.gui_queue.put(f"Error initiating download: {e}")

    def delete_file(self, filename):
        try:
            self.client_socket.send(f"DELETE {filename}".encode())
            # Do NOT perform recv here; listener thread will handle the response
        except Exception as e:
            self.gui_queue.put(f"Error deleting file: {e}")

    def log_message(self, message):
        self.gui_queue.put(message)

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
        scrollbar = Scrollbar(self.root, command=self.log_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_listbox.config(yscrollcommand=scrollbar.set)

        # Start processing the GUI queue
        self.process_gui_queue()

        self.root.protocol("WM_DELETE_WINDOW", self.disconnect_gui)
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

        try:
            port_num = int(port)
            if not (0 < port_num < 65536):
                raise ValueError
        except ValueError:
            self.log_message("Error! Port must be a valid integer between 1 and 65535.")
            return

        # Validate username
        if not username:
            self.log_message("Error! Username cannot be empty.")
            return

        # Attempt to connect
        if self.connect_to_server(ip, port_num, username):
            messagebox.showinfo("Success", f"Connected to {ip}:{port_num} as '{username}'.")
        else:
            messagebox.showerror("Error", "Failed to connect to server.")

    def upload_gui(self):
        if not self.client_socket:
            self.log_message("Not connected to a server.")
            return
        file_path = filedialog.askopenfilename(filetypes=[("All files", "*.*")])
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
            self.log_message("Download cancelled: No filename provided.")
            return

        owner = simpledialog.askstring("Download File", "Enter the owner's username:")
        if not owner:
            self.log_message("Download cancelled: No owner provided.")
            return

        # Prompt user to select the download directory
        download_directory = filedialog.askdirectory(title="Select Download Directory")
        if not download_directory:
            self.log_message("Download cancelled: No directory selected.")
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
            self.log_message("Delete cancelled: No filename provided.")
            return

        # Confirmation dialog
        confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{filename}'?")
        if confirm:
            self.delete_file(filename)
        else:
            self.log_message("Delete cancelled by user.")

    def disconnect_gui(self):
        self.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    client = Client()
    client.setup_gui()
