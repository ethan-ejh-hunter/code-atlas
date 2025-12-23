
import sys
import struct

def inspect_file(path):
    with open(path, 'rb') as f:
        data = f.read()

    # Search for "TEXT" chunk
    text_idx = data.find(b'TEXT')
    if text_idx == -1:
        print(f"No TEXT chunk found in {path}")
        return

    print(f"Found TEXT at offset {text_idx}")
    
    # EGWORD chunk header seems to be 4 bytes tag + 4 bytes size?
    # Let's peek around there.
    # Earlier xxd showed: 0000 000e 5445 5854 0000 00b0
    # 0000 000e = 14 (maybe length of previous chunk?)
    # 5445 5854 = TEXT
    # 0000 00b0 = 176 (Status? Size?)
    
    # Let's verify the size.
    # The bytes after TEXT might be the size.
    size_bytes = data[text_idx+4:text_idx+8]
    size = struct.unpack('>I', size_bytes)[0] # Big Endian for Mac
    print(f"Chunk size candidates: BigEndian={size}, LittleEndian={struct.unpack('<I', size_bytes)[0]}")
    
    # Try to grab content after header. content starts after size?
    # Let's assume standard IFF/RIFF style: TAG + SIZE + DATA
    # If size is 176 (0xB0), let's see what's there.
    
    # Actually, Classic Mac resource forks or data forks often use Pascal strings or specific structures.
    # Let's try to decode a block after TEXT.
    
    start = text_idx + 8
    # Just try to grab a bulk and decode
    chunk = data[start:start+2000] 
    
    encodings = ['shift_jis', 'cp932', 'euc_jp', 'utf-8', 'mac_roman']
    for enc in encodings:
        print(f"\n--- Trying {enc} ---")
        try:
            decoded = chunk.decode(enc)
            print(decoded[:200]) # Print start
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    inspect_file(sys.argv[1])
