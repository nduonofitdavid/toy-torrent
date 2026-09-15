import io
import hashlib

info_dict =  {'length': 92063, 'name': b'sample.txt', 'piece length': 32768, 'pieces': b'\xe8v\xf6z*\x88\x86\xe8\xf3k\x13g&\xc3\x0f\xa2\x97\x03\x02-n"u\xe6\x04\xa0vfVsn\x81\xff\x10\xb5R\x04\xad\x8d5\xf0\r\x93z\x02\x13\xdf\x19\x82\xbc\x8d\tr\'\xad\x9e\x90\x9a\xcc\x17'}

def calculate_info_hash(info_dict: dict, use_hex=True) -> str | bytes:
  """
  Bencodes the info dictionary, and returns the SHA-1 hash of the result
  """
  buffer = io.BytesIO()
  buffer.write(b"d")
  for key, value in info_dict.items():
    key_len = str(len(key))
    buffer.write(key_len.encode(encoding="ascii"))
    buffer.write(b":")
    buffer.write(bytes(key, encoding="utf-8"))
    
    if isinstance(value, int):
      repr = f"i{value}e"
      buffer.write(bytes(repr, encoding="utf-8"))

    elif isinstance(value, bytes):
      value_len = str(len(value))
      buffer.write(value_len.encode(encoding="ascii"))
      buffer.write(b":")
      buffer.write(value)

  buffer.write(b"e")

  buffer.seek(0) # move pointer to the start
  contents = buffer.read()
  hash_digest = hashlib.sha1(contents)
  if use_hex:
    return hash_digest.hexdigest()
  return hash_digest.digest()


def pieces_to_list(pieces: bytes):
  """
  Converts a stream of bytes representing pieces in a torrent file into
  a list of piece
  """
  res = []
  current = 0
  hash_len = 20 # according to the protocol, each hash in the pieces bytes is madeup of 20 bytes
  stop = hash_len

  while current < len(pieces):
    res.append(pieces[current:stop].hex())
    current+=hash_len
    stop+=hash_len

  return res

def encode_url(digest: str):
  res = []
  for i in range(1, len(digest), 2):
    res.append("%")
    res.append(digest[i-1])
    res.append(digest[i])
  return "".join(res)

if __name__ == "__main__":
  digest = calculate_info_hash(info_dict, use_hex=True)
  assert digest == "d69f91e6b2ae4c542468d1073a71d4ea13879a7f"
  digest_url = encode_url(digest)
  assert digest_url == "%d6%9f%91%e6%b2%ae%4c%54%24%68%d1%07%3a%71%d4%ea%13%87%9a%7f"
  res = pieces_to_list(info_dict["pieces"])

  true_piece_hashes = [
    "e876f67a2a8886e8f36b136726c30fa29703022d",
    "6e2275e604a0766656736e81ff10b55204ad8d35",
    "f00d937a0213df1982bc8d097227ad9e909acc17"
  ]

  for res_, true in zip(res, true_piece_hashes):
    assert res_ == true