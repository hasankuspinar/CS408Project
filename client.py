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
        self.socket_lock = threading.Lock()  #to use threads safely with concurrency
        self.gui_queue = queue.Queue()    #to use threads safely with concurrency   
        self.current_download = None         

    def connect_to_server(self, ip, port, username):
        max_attempts = 1
        for attempt in range(max_attempts):
            try:
                #close any existing socket
                with self.socket_lock:
                    if self.client_socket:
                        try:
                            self.client_socket.close()
                            self.client_socket = None
                        except:
                            pass
                        self.client_socket = None  #reset to None

                    #creating a new socket
                    self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

                    #setting timeout for connection
                    self.client_socket.settimeout(10)  

                    self.client_socket.connect((ip, port))

                    #setting a longer timeout for operations
                    self.client_socket.settimeout(60)  

                    #sending username
                    self.client_socket.send(username.encode())

                    #receiving a response
                    response = self.client_socket.recv(1024).decode()

                    if response == "CONNECTED":
                        self.gui_queue.put(f"Connected to server as {username}.")
                        self.username = username
                        self.server_ip = ip
                        self.server_port = port

                        #starting the listener thread
                        self.listening = True
                        self.listener_thread = threading.Thread(target=self.listen_to_server, daemon=True)
                        self.listener_thread.start()

                        return True
                    
                    #if there is an error
                    elif response.startswith("ERROR"):
                        self.gui_queue.put(response)
                        self.client_socket.close()
                        self.client_socket = None  
                        return False
                    else:
                        self.gui_queue.put(f"Unexpected response from server: {response}")
                        self.client_socket.close()
                        self.client_socket = None  
                        return False

            #if it cannot connect to the server
            except ConnectionRefusedError:
                self.gui_queue.put("Server is not open.")
                self.client_socket = None  
                return False
            except (socket.timeout, OSError) as e:
                self.gui_queue.put(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt == max_attempts - 1:
                    self.client_socket = None  
                    self.gui_queue.put("Failed to connect after multiple attempts.")
                    return False
                import time
                time.sleep(2)
                self.client_socket = None  
            except Exception as e:
                self.gui_queue.put(f"An unexpected error occurred: {e}")
                self.client_socket = None
                return False

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

                #ignore debug messages
                if decoded_message.startswith("DEBUG:"):
                    continue  

                #if the server is shutdown
                if decoded_message.startswith("SERVER_SHUTDOWN:"):
                    shutdown_msg = decoded_message.replace("SERVER_SHUTDOWN:", "").strip()
                    self.gui_queue.put(f"** Server Shutdown: {shutdown_msg} **")
                    self.disconnect()
                    break

                #handling notifications (e.g., file downloaded)
                if decoded_message.startswith("NOTIFICATION:"):
                    notification = decoded_message.replace("NOTIFICATION:", "").strip()
                    self.gui_queue.put(f"** Notification: {notification} **")
                    continue  #continue to next message

                #handling file list
                if "Owner:" in decoded_message:
                    lines = decoded_message.strip().split('\n')
                    file_entries = []
                    for line in lines:
                        if "Owner:" in line:
                            #extracting filename and owner
                            try:
                                filename_part, owner_part = line.split(" (Owner: ")
                                owner = owner_part.rstrip(")")
                                filename = filename_part.strip()
                                file_entries.append(f"{filename} - {owner}")
                            except ValueError:
                                #handle unexpected format
                                file_entries.append(f"Invalid file entry: {line}")

                    if file_entries:
                        self.gui_queue.put("File List:")
                        for entry in file_entries:
                            self.gui_queue.put(entry)
                    else:
                        self.gui_queue.put("No files available on the server.")
                    continue  #continue to next message

                #handling upload 
                if decoded_message.startswith("UPLOAD_RESPONSE:"):
                    upload_response = decoded_message.replace("UPLOAD_RESPONSE:", "").strip()
                    self.gui_queue.put(upload_response)
                    if "overwritten" in upload_response.lower():
                        filename = self.current_download['filename'] if self.current_download else "unknown"
                        self.gui_queue.put(f"SHOWINFO:File Overwritten:The file '{filename}' has been overwritten on the server.")
                    elif "uploaded successfully" in upload_response.lower():
                        filename = self.current_download['filename'] if self.current_download else "unknown"
                        self.gui_queue.put(f"SHOWINFO:Upload Successful:The file '{filename}' has been uploaded successfully.")
                    continue  #continue to next message

                #handling file download 
                if decoded_message.startswith("FILESIZE"):
                    parts = decoded_message.split(" ")
                    if len(parts) == 2:
                        try:
                            file_size = int(parts[1])
                            if self.current_download and self.current_download['filename'] and self.current_download['owner']:
                                self.current_download['file_size'] = file_size
                                #sending acknowledgment
                                self.client_socket.send("READY".encode())
                                #writing to file
                                self.current_download['file'] = open(self.current_download['save_path'], "wb")
                                self.gui_queue.put(f"Downloading file '{self.current_download['filename']}'...")
                        except ValueError:
                            self.gui_queue.put("Invalid FILESIZE value received.")
                    else:
                        self.gui_queue.put("Invalid FILESIZE response from server.")
                    continue  #continue to next message

                #handling if other messages or file data are received
                if self.current_download and self.current_download['file']:
                    try:
                        #write the incoming data to the file
                        self.current_download['file'].write(message)
                        self.current_download['bytes_received'] += len(message)
                        if self.current_download['bytes_received'] >= self.current_download['file_size']:
                            self.current_download['file'].close()
                            self.gui_queue.put(f"File '{self.current_download['filename']}' downloaded successfully.")
                            self.current_download = None
                    except Exception as e:
                        self.gui_queue.put(f"Error writing to file: {e}")
                        if self.current_download['file']:
                            self.current_download['file'].close()
                        self.current_download = None
                else:
                    self.gui_queue.put(decoded_message)
            except socket.timeout:
                continue  #continue listening
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
                if message.startswith("SHOWINFO:"):
                    #parsing the message to get the title and content
                    _, title, content = message.split(":", 2)
                    messagebox.showinfo(title, content)
                elif message.startswith("SHOWWARNING:"):
                    _, title, content = message.split(":", 2)
                    messagebox.showwarning(title, content)
                elif message.startswith("** Notification:"):
                    #notification for something like download
                    notification_text = message.replace("** Notification:", "").strip()
                    messagebox.showinfo("Notification", notification_text)
                elif message.startswith("** Server Shutdown:"):
                    #notification for server shutdown
                    shutdown_text = message.replace("** Server Shutdown:", "").strip()
                    messagebox.showwarning("Server Shutdown", shutdown_text)
                else:
                    self.log_listbox.insert(END, message)
                    self.log_listbox.yview_moveto(1)  #auto-scroll to the end
        except queue.Empty:
            pass
        except Exception as e:
            messagebox.showerror("Error", f"Error processing GUI queue: {e}")
        finally:
            #scheduling the next check after 100 milliseconds
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
            #closing any open download files
            if self.current_download and self.current_download.get('file'):
                self.current_download['file'].close()
                self.current_download = None
            self.gui_queue.put("Disconnected from server.")
            self.username = None  #reset username
        except Exception as e:
            self.gui_queue.put(f"Error disconnecting: {e}")
            self.client_socket = None  #ensure client_socket is reset
            self.username = None  #reset username

    def upload_file(self, file_path):
        if not self.client_socket:
            self.gui_queue.put("Error: Not connected to a server.")
            return

        try:
            filename = os.path.basename(file_path)
            if not os.path.exists(file_path) or not filename.strip():
                self.gui_queue.put("Error: Invalid file path or filename.")
                return

            #getting the file size
            file_size = int(os.path.getsize(file_path))

            #notifying the server about the upload, including the file size
            self.gui_queue.put(f"Uploading file '{filename}'...")
            self.client_socket.send(f"UPLOAD {filename} {file_size}".encode())

            #tracking the upload as a current download for potential overwrite notifications
            self.current_download = {
                'filename': filename,
                'owner': self.username,  #assuming uploader is the owner
                'save_path': None,       
                'file_size': 0,
                'bytes_received': 0,
                'file': None
            }

            #sending the file content
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(4096)
                    if not chunk:
                        break
                    self.client_socket.sendall(chunk)

            #not performing recv, listener thread handles the response
        except Exception as e:
            self.gui_queue.put(f"Unexpected error during upload: {e}")

    def request_file_list(self):
        try:
            if not self.client_socket:
                self.gui_queue.put("Not connected to a server.")
                return

            #request the file list from the server
            self.client_socket.send("LIST".encode())
            #not performing recv, listener thread handles the response
        except Exception as e:
            self.gui_queue.put(f"Error requesting file list: {e}")

    def download_file(self, filename, owner):
        if not self.download_directory:
            messagebox.showerror("Error", "Download directory not set.")
            return
        try:
            #if a download is already in progress
            if self.current_download and self.current_download['file']:
                self.gui_queue.put("Error: A download is already in progress.")
                messagebox.showerror("Download Error", "A download is already in progress.")
                return

            #tracking the current download
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
            #listener thread handles the rest
        except Exception as e:
            self.gui_queue.put(f"Error initiating download: {e}")

    def delete_file(self, filename):
        try:
            self.client_socket.send(f"DELETE {filename}".encode())
            #not performing recv, listener thread handles the response
        except Exception as e:
            self.gui_queue.put(f"Error deleting file: {e}")

    def log_message(self, message):
        self.gui_queue.put(message)

    def setup_gui(self):
        self.root = Tk()
        self.root.title("Client")
        self.root.geometry("600x400")

        #Server Connection Form
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

        #File Operations Buttons
        Button(self.root, text="Upload File", command=self.upload_gui).pack()
        Button(self.root, text="View Files", command=self.request_file_list).pack()
        Button(self.root, text="Download File", command=self.download_gui).pack()
        Button(self.root, text="Delete File", command=self.delete_gui).pack()
        Button(self.root, text="Disconnect", command=self.disconnect_gui).pack()

        #Log Box
        self.log_listbox = Listbox(self.root)
        self.log_listbox.pack(fill="both", expand=True)
        scrollbar = Scrollbar(self.root, command=self.log_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_listbox.config(yscrollcommand=scrollbar.set)

        #start processing the GUI queue
        self.process_gui_queue()

        self.root.protocol("WM_DELETE_WINDOW", self.disconnect_gui)
        self.root.mainloop()

    def connect_gui(self):
        ip = self.server_ip_entry.get().strip()
        port = self.port_entry.get().strip()
        username = self.username_entry.get().strip()

        #handling reconnecting
        if self.client_socket:
            response = messagebox.askyesno("Reconnect", "You are already connected. Do you want to reconnect?")
            if response:
                self.disconnect()
                import time
                time.sleep(0.5)
            else:
                return

        #checking IP address
        if not ip:
            self.log_message("Error! IP address cannot be empty.")
            return

        #checking port number
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

        #checking the username
        if not username:
            self.log_message("Error! Username cannot be empty.")
            return

        #attempting to connect
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

        #asking user to enterr file name to download
        filename = simpledialog.askstring("Download File", "Enter the filename to download:")
        if not filename:
            self.log_message("Download cancelled: No filename provided.")
            return

        #asking user to enter username of the user who uploaded it
        owner = simpledialog.askstring("Download File", "Enter the owner's username:")
        if not owner:
            self.log_message("Download cancelled: No owner provided.")
            return

        #download directory pop up
        download_directory = filedialog.askdirectory(title="Select Download Directory")
        if not download_directory:
            self.log_message("Download cancelled: No directory selected.")
            return

        #setting the download directory and proceeding
        self.download_directory = download_directory
        self.log_message(f"Download directory set to: {self.download_directory}")
        self.download_file(filename, owner)

    def delete_gui(self):
        if not self.client_socket:
            self.log_message("Not connected to a server.")
            return

        #asking user to enter the filename to delete
        filename = simpledialog.askstring("Delete File", "Enter filename to delete:")
        if not filename:
            self.log_message("Delete cancelled: No filename provided.")
            return

        #confirming deletion
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
