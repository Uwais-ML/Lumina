with open('/Users/apple/Lumina/logs/llamafile_Phi-3.5-mini-instruct-Q4_K_M.log') as f:
    for line in f:
        if 'eval time' in line and 'prompt eval time' not in line:
            # 1. grab the part inside ( ... )
            inside = line[line.find('(') + 1 : line.find(')')]
            # inside = "   92.88 ms per token,    10.77 tokens per second"

            # 2. split on comma, take the second piece
            second = inside.split(',')[1]
            # second = "    10.77 tokens per second"

            # 3. take the first token of that piece
            value = float(second.split()[0])
            