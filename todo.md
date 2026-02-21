# LNG-GraphRAG Project TODO

## Next Steps (priority)
- [ ] **Speaker diarization** (deferred): Integrate [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) to label “who spoke when” in audio (requires Hugging Face token + accepting model conditions).
- [x] **Full-span transcriptions**: Ensure transcriptions cover the entire timestamp span (fixed in `simple_asr.py`: dynamic `max_tokens` per chunk; split by silence).
- [x] **Layout & color**: Collapsible hamburger menu panel on the left; color palette `#525252`, `#614000`, `#D39B05`, `#FEAE02`, `#1E1E1E` applied across the dashboard.

## Future Goals
- [ ] Complete GraphRAG implementation
- [ ] Integrate Breeze-ASR-25 for audio processing
- [ ] Implement VOD processing pipeline
- [ ] Add comprehensive documentation
- [ ] Set up CI/CD pipeline
- [ ] Add unit tests
- [ ] Performance optimization

## Completed Tasks
- [x] Initialize git repository
- [x] Create project structure
- [x] Set up Breeze-ASR-25 component
- [x] Create VODs download functionality
- [x] Embedding backend switch: nomic / openai / both; store as `nomic_embeddings` and `openai_embeddings` on Chunk/Concept nodes
- [x] `run_embeddings_to_neo4j.py` with `--embedding` and `--clean`; ensure Neo4j running + optional Ollama nomic pull
- [x] `load_single_to_neo4j.py` for adding one transcription or one WAV to existing Neo4j (no DB wipe)
- [x] `find_transcriptions_without_timestamps.py` to list transcriptions missing timecodes and map to videos.csv
- [x] `redownload_rerun_no_timestamps.py` to redownload videos and rerun ASR for same format with timestamps
- [x] Neo4j Community Edition support: use default DB `neo4j` when named DBs not available
- [x] Documentation updates (README, NEO4J_SETUP, NEO4J_BACKUP) for embeddings, single-file load, and timestamp tools
- [x] Manual chunk update: `update_chunk_in_neo4j` supports `embedding_backend` (nomic / openai / both) so both embeddings stay in sync when fixing transcriptions
- [x] Ollama option for NL query LLM (`NL_QUERY_LLM=ollama`, `OLLAMA_NL_MODEL`) to save OpenAI token cost
- [x] Transcriptions tab split view: left = scrollable list + chunks, right = fixed YouTube player (URL from `videos.csv`)

## Notes
- Project combines GraphRAG with audio processing capabilities
- Breeze-ASR-25 provides speech recognition functionality
- VODs module handles video content processing
- Chunk/Concept nodes use `nomic_embeddings` and/or `openai_embeddings` (vector indexes: `chunk_nomic_embeddings`, `chunk_openai_embeddings`, etc.)
