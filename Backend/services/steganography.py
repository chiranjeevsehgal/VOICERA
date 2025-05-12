import wave
import json
import numpy as np
import uuid
import hashlib
import io
import os
from typing import Dict, Any, Tuple, Optional, BinaryIO
from fastapi import HTTPException, UploadFile

class AudioSteganography:
   """Class for embedding and extracting metadata in audio files using steganography."""

   @staticmethod
   def calculate_checksum(audio_data: bytes) -> str:
       """Calculate SHA-256 checksum of audio data."""
       return hashlib.sha256(audio_data).hexdigest()

   @staticmethod
   def convert_to_binary(data: str) -> str:
       """Convert string data to binary string."""
       binary = ''.join(format(ord(char), '08b') for char in data)
       return binary
   
   @staticmethod
   def binary_to_string(binary_str: str) -> str:
       """Convert binary string back to text."""
       string_data = ''
       for i in range(0, len(binary_str), 8):
           byte = binary_str[i:i+8]
           if len(byte) == 8:  # Ensure we have a full byte
               string_data += chr(int(byte, 2))
       return string_data

   def embed_metadata_lsb(self, 
                         audio_file: BinaryIO, 
                         metadata: Dict[str, Any],
                         output_path: Optional[str] = None) -> Tuple[str, bytes]:
       """
       Embed metadata into audio file using LSB steganography.
       
       Args:
           audio_file: Audio file object
           metadata: Dictionary containing metadata to embed
           output_path: Optional path to save the modified audio file
           
       Returns:
           Tuple containing file path and modified audio data
       """
       try:
           # Add identifier and version to ensure we can detect our steganography
           metadata["stego_version"] = "1.0"
           metadata["stego_id"] = str(uuid.uuid4())
           
           # Convert metadata to JSON and then to binary
           metadata_json = json.dumps(metadata)
           binary_metadata = self.convert_to_binary(metadata_json)
           
           # Add length information at the beginning (32 bits for length)
           length_binary = format(len(binary_metadata), '032b')
           binary_data = length_binary + binary_metadata
           
           # Read audio file
           with wave.open(audio_file, 'rb') as audio:
               params = audio.getparams()
               frames = bytearray(audio.readframes(audio.getnframes()))
           
           # Check if audio file has enough capacity
           max_capacity = len(frames) // 8  # 1 bit per byte
           if len(binary_data) > max_capacity:
               raise ValueError(f"Metadata too large ({len(binary_data)} bits) for audio capacity ({max_capacity} bits)")
           
           # Embed metadata in LSBs
           for i in range(len(binary_data)):
               if i < len(frames):
                   # Set LSB of audio byte to metadata bit
                   frames[i] = (frames[i] & 0xFE) | int(binary_data[i])
           
           # Create output file
           if output_path:
               file_path = output_path
           else:
               file_path = f"temp_stego_{metadata['stego_id']}.wav"
           
           # Write modified audio to output file
           with wave.open(file_path, 'wb') as out_file:
               out_file.setparams(params)
               out_file.writeframes(frames)
           
           return file_path, bytes(frames)
           
       except Exception as e:
           raise HTTPException(
               status_code=500, 
               detail=f"Failed to embed metadata: {str(e)}"
           )

   def extract_metadata_lsb(self, audio_file: BinaryIO) -> Dict[str, Any]:
       """
       Extract metadata from audio file with LSB steganography.
       
       Args:
           audio_file: Audio file object
           
       Returns:
           Dictionary containing extracted metadata
       """
       try:
           # Read audio file
           with wave.open(audio_file, 'rb') as audio:
               frames = bytearray(audio.readframes(audio.getnframes()))
           
           # Extract length information (first 32 bits)
           length_binary = ''.join(str(frame & 1) for frame in frames[:32])
           metadata_length = int(length_binary, 2)
           
           # Extract metadata bits
           metadata_binary = ''.join(str(frame & 1) for frame in frames[32:32+metadata_length])
           
           # Convert binary back to string and then to JSON
           metadata_json = self.binary_to_string(metadata_binary)
           metadata = json.loads(metadata_json)
           
           # Check if this is actually our steganography format
           if "stego_version" not in metadata or "stego_id" not in metadata:
               raise ValueError("No valid steganographic metadata found")
           
           return metadata
           
       except json.JSONDecodeError:
           raise HTTPException(
               status_code=400, 
               detail="Invalid steganographic data: could not decode JSON"
           )
       except Exception as e:
           raise HTTPException(
               status_code=500, 
               detail=f"Failed to extract metadata: {str(e)}"
           )

   def embed_with_echo_hiding(self, 
                             audio_file: BinaryIO, 
                             metadata: Dict[str, Any],
                             output_path: Optional[str] = None) -> Tuple[str, bytes]:
       """
       Embed metadata using echo hiding technique.
       
       This is a more robust technique than LSB that can survive some
       audio processing and compression.
       
       Args:
           audio_file: Audio file object
           metadata: Dictionary containing metadata to embed
           output_path: Optional path to save the modified audio file
           
       Returns:
           Tuple containing file path and modified audio data
       """
       # Note: This is a placeholder for the echo hiding implementation
       # A complete implementation would require more complex DSP operations
       raise NotImplementedError("Echo hiding not yet implemented")

   def embed_with_phase_coding(self, 
                              audio_file: BinaryIO, 
                              metadata: Dict[str, Any],
                              output_path: Optional[str] = None) -> Tuple[str, bytes]:
       """
       Embed metadata using phase coding technique.
       
       This technique modifies the phase of audio frequency components,
       which is less perceptible to human hearing.
       
       Args:
           audio_file: Audio file object
           metadata: Dictionary containing metadata to embed
           output_path: Optional path to save the modified audio file
           
       Returns:
           Tuple containing file path and modified audio data
       """
       # Note: This is a placeholder for the phase coding implementation
       # A complete implementation would require FFT and phase manipulation
       raise NotImplementedError("Phase coding not yet implemented")

   def embed_metadata(self, 
                     audio_file: BinaryIO, 
                     metadata: Dict[str, Any], 
                     method: str = "lsb",
                     output_path: Optional[str] = None) -> Tuple[str, bytes]:
       """
       Embed metadata into audio file using specified steganography method.
       
       Args:
           audio_file: Audio file object
           metadata: Dictionary containing metadata to embed
           method: Steganography method to use ('lsb', 'echo', 'phase')
           output_path: Optional path to save the modified audio file
           
       Returns:
           Tuple containing file path and modified audio data
       """
       if method == "lsb":
           return self.embed_metadata_lsb(audio_file, metadata, output_path)
       elif method == "echo":
           return self.embed_with_echo_hiding(audio_file, metadata, output_path)
       elif method == "phase":
           return self.embed_with_phase_coding(audio_file, metadata, output_path)
       else:
           raise ValueError(f"Unsupported steganography method: {method}")

   def extract_metadata(self, audio_file: BinaryIO, method: str = "lsb") -> Dict[str, Any]:
       """
       Extract metadata from audio file using specified steganography method.
       
       Args:
           audio_file: Audio file object
           method: Steganography method used ('lsb', 'echo', 'phase')
           
       Returns:
           Dictionary containing extracted metadata
       """
       if method == "lsb":
           return self.extract_metadata_lsb(audio_file)
       elif method == "echo":
           raise NotImplementedError("Echo hiding extraction not yet implemented")
       elif method == "phase":
           raise NotImplementedError("Phase coding extraction not yet implemented")
       else:
           raise ValueError(f"Unsupported steganography method: {method}")

   def process_audio_with_steganography(self, 
                                       audio_path: str, 
                                       transcription: str, 
                                       metadata: Dict[str, Any],
                                       method: str = "lsb") -> str:
       """
       Process audio file by embedding essential metadata.
       
       Args:
           audio_path: Path to the audio file
           transcription: Text transcription of the audio
           metadata: Complete metadata dictionary
           method: Steganography method to use
           
       Returns:
           Path to the processed audio file
       """
       # Create compact essential metadata
       essential_metadata = {
           "id": str(uuid.uuid4()),
           "timestamp": metadata.get("timestamp", None),
           "checksum": self.calculate_checksum(open(audio_path, "rb").read()),
           "keywords": metadata.get("keywords", []),
           "vector_id": metadata.get("vector_id", None),
           "duration": metadata.get("duration", None)
       }
       
       # Add a small sample of the transcription (first 100 chars)
       essential_metadata["transcription_sample"] = transcription[:100] if transcription else ""
       
       # Embed essential metadata using steganography
       with open(audio_path, "rb") as audio_file:
           stego_audio_path, _ = self.embed_metadata(
               audio_file, 
               essential_metadata, 
               method=method,
               output_path=f"{os.path.splitext(audio_path)[0]}_stego.wav"
           )
       
       return stego_audio_path

# Usage example:
# stego = AudioSteganography()
# processed_path = stego.process_audio_with_steganography(
#     "original.wav", 
#     "This is the transcription of the audio", 
#     {"keywords": ["test", "audio"], "vector_id": "vec123"}
# )