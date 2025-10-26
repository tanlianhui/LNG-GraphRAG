# LNG-GraphRAG

A comprehensive GraphRAG (Graph Retrieval-Augmented Generation) project that combines advanced audio processing with graph-based knowledge retrieval.

## Project Overview

This project integrates multiple components to create a powerful GraphRAG system:

- **Breeze-ASR-25**: Advanced speech recognition capabilities
- **VODs**: Video content processing and download functionality
- **GraphRAG**: Knowledge graph construction and retrieval

## Features

- 🎤 **Audio Processing**: High-quality speech recognition using Breeze-ASR-25
- 📹 **Video Processing**: Enhanced YouTube video download with anti-detection measures
- 🧠 **GraphRAG**: Intelligent knowledge graph construction and retrieval
- 🔄 **Modular Design**: Flexible architecture for easy extension
- 🛡️ **Anti-Detection**: Advanced retry logic, user-agent rotation, and cookie authentication
- 🔧 **Error Handling**: Comprehensive error handling with detailed user feedback

## Getting Started

### Prerequisites

- Python 3.8+
- Git

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd LNG-GraphRAG
```

2. Set up the environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Usage

#### YouTube Video Download

1. **Export Cookies** (Required to avoid 403 errors):
```bash
python VODs/export_cookies_guide.py
```

2. **Download Videos**:
```bash
python VODs/download_from_youtube.py
```

3. **Process with ASR**:
```bash
python run_batch_asr.py
```

#### Testing

Run the UI to test functionality:
```bash
python launch_ui.py
```

## Project Structure

```
LNG-GraphRAG/
├── Breeze-ASR-25/          # Speech recognition module
├── VODs/                   # Video processing module
├── todo.md                 # Project roadmap and tasks
└── README.md              # This file
```

## Contributing

Please see our [todo.md](todo.md) for current development goals and tasks.

## License

[License information to be added]

## Roadmap

See [todo.md](todo.md) for detailed project roadmap and completed tasks.
