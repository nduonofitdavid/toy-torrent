from urllib.parse import unquote

import sys
print(sys.argv)

def parse_magnetlink(link: str, verify_tor=False):
  keys = {}
  skip = 8
  if link[:skip] != "magnet:?":
    raise Exception("Invalid magnet link")

  def add_val(dict, key, val):
    val = unquote(val)
    if key in dict:
      store = dict[key]
      if isinstance(store, list):
        dict[key].append(val)
      else:
        dict[key] = [dict[key], val]
    else:
      dict[key] = val
  
  start = skip
  end = start+1
  key_ = None
  while end < (len(link)):
    curr = link[end]
    if curr == "=":
      key_ = link[start:end]
      start=end+1
      end+=1
      continue
    elif curr == "&":
      if key_:
        add_val(keys, key_, link[start:end])
        start=end+1
        end+=1
        continue
      else:
        raise Exception("The magnet link is malformed")

    end+=1
    if end == len(link):
      if key_:
        add_val(keys, key_, link[start:end])
        continue
      raise Exception("The magnet link is malformed")

  # verifying xt
  if "xt" not in keys:
    raise Exception("The xt query parameter was not found in the magnet link")

  if verify_tor:
    v = keys["xt"]
    if v[:9] != "urn:btih:":
      raise Exception("The magnet link provided is not a bittorrent magnet link")
    keys["xt"] = v[9:]

  return keys

print(parse_magnetlink("magnet:?xt=urn:btih:ad42ce8109f54c99613ce38f9b4d87e70f24a165&dn=magnet1.gif&tr=http%3A%2F%2Fbittorrent-test-tracker.codecrafters.io%2Fannounce", verify_tor=True))
print(parse_magnetlink("magnet:?xt=1&"))
print(parse_magnetlink("magnet:?xt=urn:btih:ad42ce8109f54c99613ce38f9b4d87e70f24a165"))