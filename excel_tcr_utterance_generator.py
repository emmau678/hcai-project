import ast

def tcr_from_ast(node):
    if isinstance(node, ast.Attribute):
        if node.attr == 'shape':
            return ['shape', tcr_from_ast(node.value)]
        else:
            base = tcr_from_ast(node.value)
            return ['attribute', base, node.attr]
    elif isinstance(node, ast.Subscript):
        if isinstance(node.slice, ast.BinOp):
            left = tcr_from_ast(node.slice.left)
            right = tcr_from_ast(node.slice.right)
            op = {
                ast.Eq: "is",
                ast.Add: "+",
                ast.Sub: "-",
                ast.Mult: "*",
                ast.Div: "/",
                ast.BitAnd: "and",
                ast.BitOr: "or"
            }.get(type(node.slice.op), "unknown operation")
            return ['select_rows', left, op, right]
        elif isinstance(node.slice, ast.Compare):
            left = tcr_from_ast(node.slice.left)
            right = tcr_from_ast(node.slice.comparators[0])
            op = {
                ast.Eq: "is"
            }.get(type(node.slice.ops[0]), "unknown operation")
            return ['select_rows', left, op, right]
        elif isinstance(node.value, ast.Attribute) and node.value.attr == 'shape':
            idx = node.slice.value
            return ['shape', tcr_from_ast(node.value), idx]
        else:
        # If it's an ast.Index, get the value from inside
            slice_value = node.slice.value if isinstance(node.slice, ast.Index) else node.slice
            # If it's a simple string or value
            col_name = slice_value.s if isinstance(slice_value, ast.Str) else slice_value.value

            return ['column_access', tcr_from_ast(node.value), col_name]
    elif isinstance(node, ast.Compare):
        left = tcr_from_ast(node.left)
        right = tcr_from_ast(node.comparators[0])
        op = node.ops[0]
        operation = {
            ast.Gt: ">",
            ast.GtE: ">=",
            ast.Lt: "<",
            ast.LtE: "<=",
            ast.Eq: "==",
            ast.NotEq: "!="
        }.get(type(op), "unknown operation")
        return ['compare', left, operation, right]
    elif isinstance(node, ast.BoolOp):
        values = [tcr_from_ast(val) for val in node.values]
        operation = {
            ast.And: "and",
            ast.Or: "or"
        }.get(type(node.op), "unknown operation")
        return ['bool_op', operation, values]
    elif isinstance(node, ast.BinOp):
        left = tcr_from_ast(node.left)
        right = tcr_from_ast(node.right)
        operation = {
            ast.Add: "added to",
            ast.Sub: "subtracted from",
            ast.Mult: "multiplied by",
            ast.Div: "divided by",
            ast.Mod: "mod",
            ast.Pow: "to the power of",
            ast.BitAnd: "and",
            ast.BitOr: "or"
        }.get(type(node.op), "unknown operation")
        return ['arithmetic_op', operation, left, right]
    elif isinstance(node, ast.Call):
        func = tcr_from_ast(node.func)
        args = [tcr_from_ast(arg) for arg in node.args]
        return ['function_call', func, args]
    elif isinstance(node, ast.Assign):
        target = tcr_from_ast(node.targets[0])
        value = tcr_from_ast(node.value)
        return ['assign', target, value]
    elif isinstance(node, ast.Str):
        return ['string', node.s]
    elif isinstance(node, ast.Name):
        return ['variable', node.id]
    elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return ['number', node.value]
    elif isinstance(node, ast.Expr):
        return tcr_from_ast(node.value)
    else:
        return []


def generate_utterance(tcr):
    steps = []

    if not tcr:
        return steps

    if tcr[0] == 'column_access':
        steps.extend(generate_utterance(tcr[1]))
        steps.append(f'select column “{tcr[2]}”')
    elif tcr[0] == 'attribute':
        base_steps = generate_utterance(tcr[1])
        steps.extend(base_steps)
    elif tcr[0] == 'function_call':
        if len(tcr) > 1:
            if tcr[1][2] == 'count':
                if len(tcr[2]) > 0:
                    steps.append(f'count “{tcr[2][0][1]}” from {generate_utterance(tcr[1])[0]}')
                else:
                    steps.extend(generate_utterance(tcr[1]))
                    steps.append("count")
            elif tcr[1][2] == 'split':
                steps.extend(generate_utterance(tcr[1]))
                steps.append(f'split the text on “{tcr[2][0][1]}”')
            elif tcr[1][2] == 'len':
                steps.extend(generate_utterance(tcr[1]))
                steps.append(f'get length')
        else:
            steps.append(tcr[1][2])
    elif tcr[0] == 'assign':
        target_utterance = generate_utterance(tcr[1])[0].replace("select", "create")
        value_utterance = generate_utterance(tcr[2])
        steps.append(target_utterance)
        steps.extend(value_utterance)
    elif tcr[0] == 'string':
        steps.append(f'“{tcr[1]}”')
    elif tcr[0] == 'arithmetic_op':
        left = generate_utterance(tcr[2])
        right = generate_utterance(tcr[3])
        steps.append(f"{left[0]} {tcr[1]} {right[0]}".replace("select", ""))
    elif tcr[0] == 'bool_op':
        val_steps = [generate_utterance(val)[0] for val in tcr[2]]
        op = operation_map.get(tcr[1], "unknown operation")
        joined_vals = f" {op} ".join(val_steps)
        print(f"DEBUG: bool_op joined_vals: {joined_vals}")
        steps.append(joined_vals)

    elif tcr[0] == 'compare':
        left = generate_utterance(tcr[1])[0]
        right = generate_utterance(tcr[3])[0]
        
        operation_map = {
            '>': "greater than",
            '>=': "greater than or equal to",
            '<': "less than",
            '<=': "less than or equal to",
            '==': "equal to",
            '!=': "not equal to",
            'and': "and",
            'or': "or"
        }
        op = operation_map.get(tcr[2], "unknown operation")
        
        steps.append(f'{left} {op} {right}'.replace("select", ""))
    elif tcr[0] == 'number':
        steps.append(format(tcr[1]))

    elif tcr[0] == 'select_rows':
        column_name = generate_utterance(tcr[1])[0]
        condition = generate_utterance(tcr[3])[0]
        steps.append(f"select rows where {column_name} {tcr[2]} {condition}")

    elif tcr[0] == 'shape':
        steps.append(generate_utterance(tcr[1])[0])
        steps.append(f"return number of rows")

    final_steps = []
    for step in steps:
        if step == 'str':
            continue
        elif step == 'len':
            final_steps.append('get length')
        else:
            final_steps.append(step)

    return final_steps

def process_multiline_code(code_sample):
    # Parse the multi-line code sample into individual statements
    parsed_code = ast.parse(code_sample)
    
    # Iterate over each statement and generate the corresponding utterance
    all_steps = []
    for stmt in parsed_code.body:
        tcr = tcr_from_ast(stmt)
        steps = generate_utterance(tcr)
        all_steps.extend(steps)
    
    return all_steps

##
## Some sample code snippets that can be run to test the functionality
##

# Multi-line code sample
#code_sample = """
#df['good'] = ((df['yr_built'] >= 1970) & (df['sqft_basement'] != 0) & (df['yr_renovated'] != 0))
#"""

#code_sample = """
#df['Mission Length'] = df['Space Flight (hr)'] / df['Missions'].str.count('STS')
#"""

#code_sample = """
#df['mission_count'] = df['Missions'].str.split(',').str.len()
#df['Space Flight (hr)'] = df['Space Flight (hr)'] / df['mission_count']
#"""

code_sample = """
df['Average Mission Time'] = df['Space Flight (hr)'] / df['Missions'].str.count('\(')
"""

#code_sample = """
#df[df['Winner'] == 'New Orleans Saints'].shape[0]
#"""

#code_sample = """
#df[df['Host City'] == 'New Orleans'].shape[0] 
#"""

#code_sample = """
#df[df['Host City'] == 'New Orleans']['Winner'].count() 
#"""

#code_sample = """
#df[(df['yr_built'] > 1970) & (df['yr_renovated'] != 0) &
# (df['sqft_basement'] != 0)]
#"""

steps = process_multiline_code(code_sample)
for i, step in enumerate(steps):
    print(f"({i+1}) {step}")
