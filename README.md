# Computer Networks File Sharing Project

This project is a **file-sharing system** using Python's `socket` module and Tkinter for GUI. It allows clients to connect to a central server for file operations like uploading, downloading, listing, and deleting files.

## Features

### Server
- Accepts multiple clients simultaneously.
- Handles file upload, download, and deletion (owners only).
- Provides a list of available files with owner information.
- Logs server activities and errors.

### Client
- Connect to the server with a username.
- Upload, download, view, and delete files.
- Receive notifications for downloads and server shutdowns.
- User-friendly GUI for easy operations.

## Prerequisites
- Python 3.x
- Required libraries: `socket`, `threading`, `queue`, `tkinter` (pre-installed with Python).

## How to Run

### Server
1. Run the server:
   ```bash
   python server.py
   ```
2. Set the port and file storage directory via the GUI.

### Client
1. Run the client:
   ```bash
   python client.py
   ```
2. Enter the server's IP, port, and your username in the GUI.
3. Use the buttons to upload, download, view, or delete files.

## Notes
- Only file owners can delete their files.
- Server notifies file owners when their files are downloaded.
- Clients are notified if the server shuts down.



