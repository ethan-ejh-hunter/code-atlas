
import sys

def is_sjis_byte(b):
    return (0x20 <= b <= 0x7E) or (0xA1 <= b <= 0xDF)

def is_sjis_lead(b):
    return (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xEA) # Extended range?

def is_sjis_trail(b):
    return (0x40 <= b <= 0x7E) or (0x80 <= b <= 0xFC)

def extract_sjis(path):
    with open(path, 'rb') as f:
        data = f.read()
    
    found_strings = []
    current_bytes = bytearray()
    
    i = 0
    length = len(data)
    
    while i < length:
        b = data[i]
        
        # Check double byte
        if is_sjis_lead(b):
            if i + 1 < length:
                b2 = data[i+1]
                if is_sjis_trail(b2):
                    current_bytes.append(b)
                    current_bytes.append(b2)
                    i += 2
                    continue
        
        # Check single byte (ASCII + Half-width Kana)
        if is_sjis_byte(b):
            current_bytes.append(b)
            i += 1
            continue
            
        # If we hit a non-SJIS byte, verify if we have a valid string accumulated
        if len(current_bytes) > 0:
            try:
                # Filter out strings that are just pure ASCII noise if needed, 
                # but user wants headers too probably.
                # Let's keep strings > 3 bytes.
                if len(current_bytes) > 3:
                     s = current_bytes.decode('shift_jis')
                     # Filter out garbage that accidentally parsed as SJIS?
                     # Common garbage: lots of punctuation or weird chars.
                     # But real text includes punctuation.
                     print(s)
            except:
                pass
            current_bytes = bytearray()
        
        i += 1
        
    # Flush last
    if len(current_bytes) > 3:
        try:
             print(current_bytes.decode('shift_jis'))
        except: pass

if __name__ == "__main__":
    extract_sjis(sys.argv[1])
