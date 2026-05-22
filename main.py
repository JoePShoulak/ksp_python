import krpc


#TODO:  dupe move to helper or delete
def safe_connect(name):
  try:
    conn = krpc.connect(name=name)
  except ConnectionRefusedError:
    print("!== Error making connection. Is there a reachable kRPC running in KSP? ==!")
    return False, False
  
  vessel = conn.space_center.active_vessel
  return conn, vessel
  
conn, vessel = safe_connect("test")

processor_part = vessel.parts.with_title("CX-4181 Scriptable Control System")[0]
processor = next((module for module in processor_part.modules if module.name == "kOSProcessor" ), None)

if processor: print(processor)

for f in processor.fields:
  print(f)

for e in processor.events:
  print(e)

for a in processor.actions:
  print(a)