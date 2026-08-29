import re

# Read the malformed file
with open('cookies.txt', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

# Parse and reformat
formatted_lines = []
for line in lines:
    line = line.strip()
    if not line or line.startswith('#'):
        formatted_lines.append(line)
        continue
    
    # Try to parse: .domain + TRUE/FALSE + / + TRUE/FALSE + digits + name + value
    match = re.match(r'^(\.youtube\.com)(TRUE|FALSE)(/)([TRUE|FALSE]+)(\d+)(.+)$', line)
    if match:
        domain, flag1, path, flag2, expiry, rest = match.groups()
        
        # Split rest into name and value (name is uppercase/underscores/numbers, value is the rest)
        name_match = re.match(r'^([A-Z_\-\d]+)(.*)$', rest)
        if name_match:
            name, value = name_match.groups()
            # Make sure name and value are not empty
            if name and value:
                formatted = f"{domain}\t{flag1}\t{path}\t{flag2}\t{expiry}\t{name}\t{value}"
                formatted_lines.append(formatted)
                print(f"✓ {name[:20]}")
            else:
                print(f"✗ Skipped (empty name/value): {line[:60]}")
        else:
            print(f"✗ Could not split: {line[:60]}")
    else:
        print(f"✗ Could not match: {line[:60]}")

# Write back with tabs
with open('cookies.txt', 'w', encoding='utf-8', newline='') as f:
    f.write('\n'.join(formatted_lines) + '\n')

cookie_count = len([l for l in formatted_lines if l and not l.startswith('#')])
print(f"\n✓ Reformatted {cookie_count} cookie lines")
