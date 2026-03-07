import re

def split_text(text: str, max_length: int = 250) -> list[str]:
    # Split text into sentences using punctuation (., !, ?)
    # Keep the punctuation with the sentence
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if not sentence:
            continue
            
        if len(sentence) > max_length:
            # If a single sentence is too long, split it by words
            words = sentence.split(' ')
            for word in words:
                if len(current_chunk) + len(word) + 1 <= max_length:
                    current_chunk += (" " if current_chunk else "") + word
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = word
        else:
            if len(current_chunk) + len(sentence) + 1 <= max_length:
                current_chunk += (" " if current_chunk else "") + sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
                
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks

test_str = "Hello world. This is a test. " * 30
chunks = split_text(test_str, 250)
for i, c in enumerate(chunks):
    print(f"Chunk {i} ({len(c)}): {c}")
