#!/usr/bin/env python3
"""
LNG GraphRAG User Interface
Main interface for managing YouTube downloads and ASR processing
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import sys
from pathlib import Path
import webbrowser

# Path setup is handled by utils

from database_manager import DatabaseManager
from VODs.download_from_youtube import download_from_youtube
from simple_asr import process_audio_file

class LNGGraphRAGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("LNG GraphRAG - YouTube Download & ASR Processing")
        self.root.geometry("1200x800")
        
        # Initialize database
        self.db = DatabaseManager()
        
        # Create main interface
        self.create_interface()
        
        # Clean up any interrupted processes from previous sessions
        self.cleanup_on_startup()
        
        # Load initial data
        self.refresh_data()
    
    def cleanup_on_startup(self):
        """Clean up any interrupted processes from previous sessions"""
        try:
            cleanup_results = self.db.cleanup_interrupted_processes()
            
            if any(cleanup_results.values()):
                self.log_message("System startup cleanup completed:")
                if cleanup_results['cleaned_files'] > 0:
                    self.log_message(f"  - Reset {cleanup_results['cleaned_files']} interrupted file processes")
                if cleanup_results['cleaned_downloads'] > 0:
                    self.log_message(f"  - Reset {cleanup_results['cleaned_downloads']} interrupted downloads")
                if cleanup_results['cleaned_jobs'] > 0:
                    self.log_message(f"  - Marked {cleanup_results['cleaned_jobs']} interrupted jobs as failed")
            else:
                self.log_message("No interrupted processes found - system ready")
                
        except Exception as e:
            self.log_message(f"Warning: Could not complete startup cleanup: {e}")
    
    def create_interface(self):
        """Create the main user interface"""
        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Download tab
        self.create_download_tab(notebook)
        
        # Files tab
        self.create_files_tab(notebook)
        
        # Processing tab
        self.create_processing_tab(notebook)
        
        # Statistics tab
        self.create_statistics_tab(notebook)
    
    def create_download_tab(self, notebook):
        """Create the download management tab"""
        download_frame = ttk.Frame(notebook)
        notebook.add(download_frame, text="YouTube Downloads")
        
        # URL input section
        url_frame = ttk.LabelFrame(download_frame, text="Add YouTube URLs", padding=10)
        url_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(url_frame, text="YouTube URLs (separate multiple URLs with spaces):").pack(anchor=tk.W)
        self.url_text = scrolledtext.ScrolledText(url_frame, height=4, width=80)
        self.url_text.pack(fill=tk.X, pady=5)
        
        # Help text
        help_text = "Tip: You can paste multiple URLs at once, separated by spaces. Each URL will be added individually."
        ttk.Label(url_frame, text=help_text, font=("TkDefaultFont", 8), foreground="gray").pack(anchor=tk.W)
        
        # Buttons
        button_frame = ttk.Frame(url_frame)
        button_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(button_frame, text="Add URLs", command=self.add_url).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear URLs", command=self.clear_urls).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Delete Selected URLs", command=self.delete_selected_urls).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Download Selected", command=self.download_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Download All Pending", command=self.download_all_pending).pack(side=tk.LEFT, padx=5)
        
        # Downloads list
        downloads_frame = ttk.LabelFrame(download_frame, text="Downloads", padding=10)
        downloads_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Treeview for downloads
        columns = ("ID", "URL", "Title", "Status", "Created")
        self.downloads_tree = ttk.Treeview(downloads_frame, columns=columns, show="headings", height=10)
        
        for col in columns:
            self.downloads_tree.heading(col, text=col)
            self.downloads_tree.column(col, width=150)
        
        # Scrollbar for downloads
        downloads_scroll = ttk.Scrollbar(downloads_frame, orient=tk.VERTICAL, command=self.downloads_tree.yview)
        self.downloads_tree.configure(yscrollcommand=downloads_scroll.set)
        
        self.downloads_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        downloads_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind selection
        self.downloads_tree.bind("<<TreeviewSelect>>", self.on_download_select)
    
    def create_files_tab(self, notebook):
        """Create the files management tab"""
        files_frame = ttk.Frame(notebook)
        notebook.add(files_frame, text="Files")
        
        # File operations
        operations_frame = ttk.LabelFrame(files_frame, text="File Operations", padding=10)
        operations_frame.pack(fill=tk.X, padx=10, pady=5)
        
        button_frame = ttk.Frame(operations_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Add Local File", command=self.add_local_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Process Selected", command=self.process_selected_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Process All Pending", command=self.process_all_pending).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Delete Selected", command=self.delete_selected_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cleanup Interrupted", command=self.manual_cleanup).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Refresh", command=self.refresh_data).pack(side=tk.LEFT, padx=5)
        
        # Files list
        files_list_frame = ttk.LabelFrame(files_frame, text="Files", padding=10)
        files_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Treeview for files
        columns = ("ID", "Filename", "Type", "Status", "Size", "Duration", "Created")
        self.files_tree = ttk.Treeview(files_list_frame, columns=columns, show="headings", height=15)
        
        for col in columns:
            self.files_tree.heading(col, text=col)
            self.files_tree.column(col, width=120)
        
        # Scrollbar for files
        files_scroll = ttk.Scrollbar(files_list_frame, orient=tk.VERTICAL, command=self.files_tree.yview)
        self.files_tree.configure(yscrollcommand=files_scroll.set)
        
        self.files_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        files_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind selection and context menu
        self.files_tree.bind("<<TreeviewSelect>>", self.on_file_select)
        self.files_tree.bind("<Button-3>", self.show_file_context_menu)  # Right-click
        self.files_tree.bind("<Delete>", lambda e: self.delete_selected_files())  # Delete key
        self.files_tree.bind("<KeyPress-Delete>", lambda e: self.delete_selected_files())  # Delete key
        
        # Create context menu
        self.file_context_menu = tk.Menu(self.root, tearoff=0)
        self.file_context_menu.add_command(label="Delete Selected", command=self.delete_selected_files)
        self.file_context_menu.add_command(label="Process Selected", command=self.process_selected_file)
        self.file_context_menu.add_separator()
        self.file_context_menu.add_command(label="Refresh", command=self.refresh_data)
    
    def create_processing_tab(self, notebook):
        """Create the processing management tab"""
        processing_frame = ttk.Frame(notebook)
        notebook.add(processing_frame, text="ASR Processing")
        
        # Processing controls
        controls_frame = ttk.LabelFrame(processing_frame, text="Processing Controls", padding=10)
        controls_frame.pack(fill=tk.X, padx=10, pady=5)
        
        button_frame = ttk.Frame(controls_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Process Selected File", command=self.process_selected_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Process All Pending", command=self.process_all_pending).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cleanup Interrupted", command=self.manual_cleanup).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Stop Processing", command=self.stop_processing).pack(side=tk.LEFT, padx=5)
        
        # Processing status
        status_frame = ttk.LabelFrame(processing_frame, text="Processing Status", padding=10)
        status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Progress bar
        self.progress_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.progress_var).pack(anchor=tk.W)
        
        self.progress_bar = ttk.Progressbar(status_frame, mode='indeterminate')
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        # Log output
        ttk.Label(status_frame, text="Processing Log:").pack(anchor=tk.W, pady=(10, 0))
        self.log_text = scrolledtext.ScrolledText(status_frame, height=15, width=80)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Processing jobs list
        jobs_frame = ttk.LabelFrame(processing_frame, text="Processing Jobs", padding=10)
        jobs_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Treeview for jobs
        columns = ("ID", "File", "Type", "Status", "Started", "Completed")
        self.jobs_tree = ttk.Treeview(jobs_frame, columns=columns, show="headings", height=8)
        
        for col in columns:
            self.jobs_tree.heading(col, text=col)
            self.jobs_tree.column(col, width=120)
        
        # Scrollbar for jobs
        jobs_scroll = ttk.Scrollbar(jobs_frame, orient=tk.VERTICAL, command=self.jobs_tree.yview)
        self.jobs_tree.configure(yscrollcommand=jobs_scroll.set)
        
        self.jobs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        jobs_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    
    def create_statistics_tab(self, notebook):
        """Create the statistics tab"""
        stats_frame = ttk.Frame(notebook)
        notebook.add(stats_frame, text="Statistics")
        
        # Statistics display
        stats_display_frame = ttk.LabelFrame(stats_frame, text="Project Statistics", padding=20)
        stats_display_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create statistics labels
        self.stats_labels = {}
        stats_info = [
            ("Total Files", "total_files"),
            ("Completed Files", "completed_files"),
            ("Failed Files", "failed_files"),
            ("Total Downloads", "total_downloads"),
            ("Completed Downloads", "completed_downloads"),
            ("Total ASR Jobs", "total_asr_jobs"),
            ("Completed ASR Jobs", "completed_asr_jobs")
        ]
        
        for i, (label_text, key) in enumerate(stats_info):
            row = i // 2
            col = (i % 2) * 2
            
            ttk.Label(stats_display_frame, text=f"{label_text}:").grid(row=row, column=col, sticky=tk.W, padx=10, pady=5)
            self.stats_labels[key] = ttk.Label(stats_display_frame, text="0", font=("Arial", 12, "bold"))
            self.stats_labels[key].grid(row=row, column=col+1, sticky=tk.W, padx=10, pady=5)
        
        # Refresh button
        ttk.Button(stats_display_frame, text="Refresh Statistics", command=self.update_statistics).grid(row=len(stats_info)//2 + 1, column=0, columnspan=4, pady=20)
    
    def add_url(self):
        """Add YouTube URLs to the database (supports multiple URLs separated by spaces)"""
        urls_text = self.url_text.get("1.0", tk.END).strip()
        if not urls_text:
            messagebox.showerror("Error", "Please enter at least one YouTube URL")
            return
        
        # Split URLs by spaces and filter out empty strings
        urls = [url.strip() for url in urls_text.split() if url.strip()]
        
        if not urls:
            messagebox.showerror("Error", "No valid URLs found")
            return
        
        added_count = 0
        failed_count = 0
        failed_urls = []
        
        for url in urls:
            try:
                download_id = self.db.add_download(url)
                self.log_message(f"Added URL: {url} (ID: {download_id})")
                added_count += 1
            except Exception as e:
                self.log_message(f"Failed to add URL: {url} - {e}")
                failed_count += 1
                failed_urls.append(url)
        
        # Clear the text area
        self.url_text.delete("1.0", tk.END)
        
        # Show summary
        if added_count > 0:
            self.log_message(f"Successfully added {added_count} URL(s)")
        if failed_count > 0:
            self.log_message(f"Failed to add {failed_count} URL(s)")
            if failed_urls:
                self.log_message(f"Failed URLs: {', '.join(failed_urls)}")
        
        self.refresh_data()
    
    def clear_urls(self):
        """Clear the URL text area"""
        self.url_text.delete("1.0", tk.END)
        self.log_message("URL text area cleared")
    
    def delete_selected_urls(self):
        """Delete selected URLs from the database"""
        selection = self.downloads_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select URLs to delete")
            return
        
        # Get download IDs from selection
        download_ids = []
        urls = []
        
        for item in selection:
            values = self.downloads_tree.item(item, "values")
            download_id = values[0]
            url = values[1]
            download_ids.append(download_id)
            urls.append(url)
        
        # Confirm deletion
        if len(download_ids) == 1:
            confirm_msg = f"Are you sure you want to delete this URL?\n\n{urls[0]}\n\nThis will remove the URL from the database."
        else:
            confirm_msg = f"Are you sure you want to delete {len(download_ids)} URLs?\n\nThis will remove the URLs from the database."
        
        if not messagebox.askyesno("Confirm Deletion", confirm_msg):
            return
        
        # Delete URLs
        try:
            deleted_count = 0
            failed_count = 0
            
            for download_id in download_ids:
                success = self.db.delete_download(download_id)
                if success:
                    deleted_count += 1
                    self.log_message(f"Deleted URL: {download_ids.index(download_id) + 1}")
                else:
                    failed_count += 1
                    self.log_message(f"Failed to delete URL ID: {download_id}")
            
            # Show summary
            if deleted_count > 0:
                self.log_message(f"Successfully deleted {deleted_count} URL(s)")
            if failed_count > 0:
                self.log_message(f"Failed to delete {failed_count} URL(s)")
            
            if failed_count > 0:
                messagebox.showwarning("Partial Success", 
                    f"Deleted {deleted_count} URLs successfully.\n"
                    f"Failed to delete {failed_count} URLs.\n"
                    f"Check the log for details.")
            else:
                messagebox.showinfo("Success", f"Successfully deleted {deleted_count} URLs")
            
            # Refresh the display
            self.refresh_data()
            
        except Exception as e:
            error_msg = f"Error deleting URLs: {e}"
            self.log_message(error_msg)
            messagebox.showerror("Deletion Error", error_msg)
    
    def add_local_file(self):
        """Add a local file to the database"""
        file_path = filedialog.askopenfilename(
            title="Select Audio File",
            filetypes=[("Audio files", "*.wav *.mp3 *.m4a *.flac"), ("All files", "*.*")]
        )
        
        if file_path:
            try:
                filename = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                
                file_id = self.db.add_file(filename, file_path, "audio", file_size)
                self.log_message(f"Added local file: {filename} (ID: {file_id})")
                self.refresh_data()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add file: {e}")
    
    def download_selected(self):
        """Download selected URLs"""
        selection = self.downloads_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select downloads to process")
            return
        
        for item in selection:
            values = self.downloads_tree.item(item, "values")
            download_id = values[0]
            url = values[1]
            
            # Start download in thread
            thread = threading.Thread(target=self.download_url, args=(download_id, url))
            thread.daemon = True
            thread.start()
    
    def download_all_pending(self):
        """Download all pending URLs"""
        pending_downloads = self.db.get_downloads_by_status("pending")
        
        if not pending_downloads:
            messagebox.showinfo("Info", "No pending downloads found")
            return
        
        for download in pending_downloads:
            download_id, url, title, status, created_at, updated_at, file_id, error_message = download
            thread = threading.Thread(target=self.download_url, args=(download_id, url))
            thread.daemon = True
            thread.start()
    
    def download_url(self, download_id, url):
        """Download a single URL"""
        try:
            self.log_message(f"Starting download: {url}")
            self.db.update_download_status(download_id, "downloading")
            
            # Use the improved download function
            success, file_path = download_from_youtube(url)
            
            if success:
                if file_path and os.path.exists(file_path):
                    # Add the downloaded file to the database
                    filename = os.path.basename(file_path)
                    file_size = os.path.getsize(file_path)
                    
                    # Add file to database
                    file_id = self.db.add_file(filename, file_path, "audio", file_size)
                    
                    # Link the download to the file
                    self.db.link_download_to_file(download_id, file_id)
                    
                    self.db.update_download_status(download_id, "completed")
                    self.log_message(f"Download completed: {url} -> {filename}")
                    self.refresh_data()  # Refresh to show the new file
                else:
                    self.db.update_download_status(download_id, "completed")
                    self.log_message(f"Download completed: {url} (file path not determined)")
            else:
                self.db.update_download_status(download_id, "failed", error_message="Download failed")
                self.log_message(f"Download failed: {url}")
                
        except Exception as e:
            self.db.update_download_status(download_id, "failed", error_message=str(e))
            self.log_message(f"Download error: {e}")
    
    def process_selected_file(self):
        """Process selected files with ASR"""
        selection = self.files_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select files to process")
            return
        
        for item in selection:
            values = self.files_tree.item(item, "values")
            file_id = values[0]
            # Get the actual file path from the database
            file_data = self.db.get_file_by_id(file_id)
            if file_data:
                file_path = file_data[2]  # file_path is at index 2
            else:
                self.log_message(f"Could not find file data for ID: {file_id}")
                continue
            
            # Start processing in thread
            thread = threading.Thread(target=self.process_file_asr, args=(file_id, file_path))
            thread.daemon = True
            thread.start()
    
    def process_all_pending(self):
        """Process all pending files sequentially"""
        pending_files = self.db.get_files_by_status("pending")
        
        if not pending_files:
            messagebox.showinfo("Info", "No pending files found")
            return
        
        # Process files sequentially (one at a time)
        thread = threading.Thread(target=self.process_files_sequentially, args=(pending_files,))
        thread.daemon = True
        thread.start()
    
    def process_files_sequentially(self, pending_files):
        """Process files one by one sequentially"""
        total_files = len(pending_files)
        self.log_message(f"Starting sequential processing of {total_files} files...")
        
        for file_index, file_data in enumerate(pending_files, 1):
            file_id = file_data[0]
            # Get the actual file path from the database
            file_info = self.db.get_file_by_id(file_id)
            if file_info:
                file_path = file_info[2]  # file_path is at index 2
            else:
                self.log_message(f"Could not find file data for ID: {file_id}")
                continue
            
            self.log_message(f"[{file_index}/{total_files}] Starting processing: {os.path.basename(file_path)}")
            self.process_file_asr(file_id, file_path)
            self.log_message(f"[{file_index}/{total_files}] Completed processing: {os.path.basename(file_path)}")
        
        self.log_message(f"Sequential processing completed: {total_files} files processed")
    
    def process_file_asr(self, file_id, file_path):
        """Process a file with ASR"""
        try:
            self.log_message(f"Starting ASR processing: {file_path}")
            self.db.update_file_status(file_id, "processing")
            
            # Add processing job
            job_id = self.db.add_processing_job(file_id, "asr")
            
            # Process the file
            success = process_audio_file(file_path)
            
            if success:
                # Update file status to completed and note that original file was deleted
                self.db.update_file_status(file_id, "completed", transcription_path=f"{os.path.splitext(file_path)[0]}_combined.txt")
                self.db.update_processing_job(job_id, "completed")
                self.log_message(f"ASR processing completed: {file_path}")
                self.log_message(f"Original audio file deleted to save space")
            else:
                self.db.update_file_status(file_id, "failed", error_message="ASR processing failed")
                self.db.update_processing_job(job_id, "failed", "ASR processing failed")
                self.log_message(f"ASR processing failed: {file_path}")
                
        except Exception as e:
            self.db.update_file_status(file_id, "failed", error_message=str(e))
            self.log_message(f"ASR processing error: {e}")
    
    def stop_processing(self):
        """Stop current processing"""
        # This is a simplified implementation
        self.log_message("Processing stop requested")
    
    def refresh_data(self):
        """Refresh all data displays"""
        self.refresh_downloads()
        self.refresh_files()
        self.refresh_jobs()
        self.update_statistics()
    
    def refresh_downloads(self):
        """Refresh downloads list"""
        # Clear existing items
        for item in self.downloads_tree.get_children():
            self.downloads_tree.delete(item)
        
        # Get downloads from database
        downloads = self.db.get_downloads_by_status("all")  # You'd need to implement this method
        
        for download in downloads:
            self.downloads_tree.insert("", tk.END, values=download)
    
    def refresh_files(self):
        """Refresh files list"""
        # Clear existing items
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)
        
        # Get files from database
        files = self.db.get_all_files()
        
        for file_data in files:
            # Format file data for display
            # Handle file_size formatting
            if file_data[5] is not None:
                file_size_str = f"{file_data[5]} bytes"
            else:
                file_size_str = "Unknown"
            
            # Handle duration formatting
            if file_data[6] is not None:
                try:
                    duration_str = f"{float(file_data[6]):.2f}s"
                except (ValueError, TypeError):
                    duration_str = "Unknown"
            else:
                duration_str = "Unknown"
            
            display_data = (
                file_data[0],  # ID
                file_data[1],  # filename
                file_data[2],  # file_type
                file_data[3],  # status
                file_size_str,  # file_size
                duration_str,  # duration
                file_data[4]   # created_at
            )
            self.files_tree.insert("", tk.END, values=display_data)
    
    def refresh_jobs(self):
        """Refresh processing jobs list"""
        # Clear existing items
        for item in self.jobs_tree.get_children():
            self.jobs_tree.delete(item)
        
        # Get jobs from database
        jobs = self.db.get_processing_jobs_by_status("all")  # You'd need to implement this method
        
        for job in jobs:
            self.jobs_tree.insert("", tk.END, values=job)
    
    def update_statistics(self):
        """Update statistics display"""
        stats = self.db.get_statistics()
        
        for key, value in stats.items():
            if key in self.stats_labels:
                self.stats_labels[key].config(text=str(value))
    
    def on_download_select(self, event):
        """Handle download selection"""
        pass
    
    def on_file_select(self, event):
        """Handle file selection"""
        pass
    
    def show_file_context_menu(self, event):
        """Show context menu for files"""
        # Select the item under the cursor
        item = self.files_tree.identify_row(event.y)
        if item:
            self.files_tree.selection_set(item)
            # Show context menu
            try:
                self.file_context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.file_context_menu.grab_release()
    
    def manual_cleanup(self):
        """Manually trigger cleanup of interrupted processes"""
        try:
            cleanup_results = self.db.cleanup_interrupted_processes()
            
            if any(cleanup_results.values()):
                self.log_message("Manual cleanup completed:")
                if cleanup_results['cleaned_files'] > 0:
                    self.log_message(f"  - Reset {cleanup_results['cleaned_files']} interrupted file processes")
                if cleanup_results['cleaned_downloads'] > 0:
                    self.log_message(f"  - Reset {cleanup_results['cleaned_downloads']} interrupted downloads")
                if cleanup_results['cleaned_jobs'] > 0:
                    self.log_message(f"  - Marked {cleanup_results['cleaned_jobs']} interrupted jobs as failed")
                
                # Refresh the display
                self.refresh_data()
                messagebox.showinfo("Cleanup Complete", f"Cleaned up {sum(cleanup_results.values())} interrupted processes")
            else:
                self.log_message("No interrupted processes found")
                messagebox.showinfo("Cleanup Complete", "No interrupted processes found")
                
        except Exception as e:
            error_msg = f"Cleanup failed: {e}"
            self.log_message(error_msg)
            messagebox.showerror("Cleanup Error", error_msg)
    
    def delete_selected_files(self):
        """Delete selected files from the database"""
        selection = self.files_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select files to delete")
            return
        
        # Get file IDs from selection
        file_ids = []
        file_names = []
        
        for item in selection:
            values = self.files_tree.item(item, "values")
            file_id = values[0]
            filename = values[1]
            file_ids.append(file_id)
            file_names.append(filename)
        
        # Confirm deletion
        if len(file_ids) == 1:
            confirm_msg = f"Are you sure you want to delete '{file_names[0]}'?\n\nThis will remove the file from the database and all related processing jobs."
        else:
            confirm_msg = f"Are you sure you want to delete {len(file_ids)} files?\n\nThis will remove the files from the database and all related processing jobs."
        
        if not messagebox.askyesno("Confirm Deletion", confirm_msg):
            return
        
        # Delete files
        try:
            results = self.db.delete_multiple_files(file_ids)
            
            # Count successful and failed deletions
            successful = [r for r in results if r['success']]
            failed = [r for r in results if not r['success']]
            
            # Log results
            if successful:
                self.log_message(f"Successfully deleted {len(successful)} files:")
                for result in successful:
                    file_info = result['result']
                    self.log_message(f"  - {file_info['filename']}")
            
            if failed:
                self.log_message(f"Failed to delete {len(failed)} files:")
                for result in failed:
                    self.log_message(f"  - File ID {result['file_id']}: {result['result']}")
            
            # Show summary
            if failed:
                messagebox.showwarning("Partial Success", 
                    f"Deleted {len(successful)} files successfully.\n"
                    f"Failed to delete {len(failed)} files.\n"
                    f"Check the log for details.")
            else:
                messagebox.showinfo("Success", f"Successfully deleted {len(successful)} files")
            
            # Refresh the display
            self.refresh_data()
            
        except Exception as e:
            error_msg = f"Error deleting files: {e}"
            self.log_message(error_msg)
            messagebox.showerror("Deletion Error", error_msg)
    
    def log_message(self, message):
        """Add message to log"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

def main():
    root = tk.Tk()
    app = LNGGraphRAGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
