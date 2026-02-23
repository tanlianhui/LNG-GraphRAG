# LNG GraphRAG User Interface

A comprehensive GUI application for managing YouTube downloads and ASR processing with database status tracking.

## Features

### 🎬 YouTube Download Management
- Add YouTube URLs for download
- Batch download multiple URLs
- Track download status (pending, downloading, completed, failed)
- Automatic retry with anti-detection measures

### 📁 File Management
- Add local audio files
- Track file status and metadata
- View file statistics (size, duration, type)
- Manage file processing queue
- Delete files from database
- Right-click context menu for quick actions

### 🎤 ASR Processing
- Process audio files with Breeze-ASR-25 model
- Save transcriptions after each chunk
- Create combined transcription files
- Track processing jobs and status

### 📊 Database Status Tracking
- MySQL database (same as web app auth; start with `docker-compose up -d mysql`)
- Track files, downloads, and processing jobs
- View comprehensive statistics
- Monitor progress and errors

## Installation

1. Install required dependencies:
```bash
pip install torch torchaudio transformers datasets yt-dlp
```

2. Run the application:
```bash
python launch_ui.py
```

## Usage

### Adding YouTube URLs
1. Go to the "YouTube Downloads" tab
2. Enter a YouTube URL in the text field
3. Click "Add URL" to add it to the database
4. Select URLs and click "Download Selected" or "Download All Pending"

### Adding Local Files
1. Go to the "Files" tab
2. Click "Add Local File" to browse for audio files
3. Files will be added to the database with "pending" status

### Deleting Files
1. Go to the "Files" tab
2. Select one or more files to delete
3. Use one of these methods:
   - Click "Delete Selected" button
   - Right-click and select "Delete Selected"
   - Press Delete key
4. Confirm deletion in the dialog
5. Files and all related data will be removed from the database

### ASR Processing
1. Go to the "ASR Processing" tab
2. Select files from the Files tab
3. Click "Process Selected File" or "Process All Pending"
4. Monitor progress in the log output
5. Transcriptions will be saved to the `./transcriptions/` directory

### Viewing Statistics
1. Go to the "Statistics" tab
2. View project statistics including:
   - Total files and downloads
   - Completed vs failed counts
   - ASR processing statistics

## File Structure

```
LNG-GraphRAG/
├── lng_ui.py              # Main UI application
├── database_manager.py    # Database management
├── launch_ui.py          # Application launcher
├── simple_asr.py         # ASR processing
├── VODs/
│   ├── download_from_youtube.py
│   └── videos.csv
└── transcriptions/       # Output directory for transcriptions
```

## Database Schema

### Files Table
- `id`: Primary key
- `filename`: File name
- `file_path`: Full file path
- `file_type`: Type of file (audio, video, etc.)
- `status`: Processing status (pending, processing, completed, failed)
- `file_size`: File size in bytes
- `duration`: Audio duration in seconds
- `transcription_path`: Path to transcription file
- `error_message`: Error details if failed

### Downloads Table
- `id`: Primary key
- `url`: YouTube URL
- `title`: Video title
- `status`: Download status
- `file_id`: Reference to files table
- `error_message`: Error details if failed

### Processing Jobs Table
- `id`: Primary key
- `file_id`: Reference to files table
- `job_type`: Type of processing (asr, etc.)
- `status`: Job status
- `started_at`: Job start time
- `completed_at`: Job completion time
- `error_message`: Error details if failed

## Troubleshooting

### Common Issues

1. **Missing Dependencies**: Run `pip install -r requirements.txt`
2. **Unicode Errors**: Ensure your terminal supports UTF-8 encoding
3. **Download Failures**: Check your internet connection and YouTube access
4. **ASR Processing Errors**: Ensure audio files are in supported formats

### Log Output

The application provides detailed logging in the "ASR Processing" tab. Check the log for:
- Download progress and errors
- ASR processing status
- File operations
- Database updates

## Advanced Features

### Batch Processing
- Process multiple files simultaneously
- Automatic retry on failures
- Progress tracking and status updates

### Database Management
- Persistent storage across sessions
- Comprehensive status tracking
- Error logging and recovery

### File Organization
- Automatic file organization
- Transcription chunking
- Combined output files

## Support

For issues or questions:
1. Check the log output for error messages
2. Verify all dependencies are installed
3. Ensure file permissions are correct
4. Check database file permissions
