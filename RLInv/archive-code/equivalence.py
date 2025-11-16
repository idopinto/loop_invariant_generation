from z3.z3 import Int, And, Or, Not, Solver, Array, Select, IntSort, unsat, sat
import pycparser
from pycparser import c_ast

class CToZ3Converter(c_ast.NodeVisitor):
    """Convert pycparser AST to Z3 expressions."""
    
    def __init__(self):
        self.variables = {}  # Cache of Z3 variables
        self.z3_expr = None
    
    def get_or_create_var(self, name):
        """Get or create a Z3 Int variable (type-agnostic approach)."""
        if name not in self.variables:
            self.variables[name] = Int(name)
        return self.variables[name]
    
    def visit_BinaryOp(self, node):
        """Handle binary operations like +, -, ==, &&, etc."""
        left = self.visit(node.left)
        right = self.visit(node.right)
        
        op = node.op
        if op == '+':
            return left + right
        elif op == '-':
            return left - right
        elif op == '*':
            return left * right
        elif op == '/':
            return left / right
        elif op == '%':
            return left % right
        elif op == '==':
            return left == right
        elif op == '!=':
            return left != right
        elif op == '<':
            return left < right
        elif op == '<=':
            return left <= right
        elif op == '>':
            return left > right
        elif op == '>=':
            return left >= right
        elif op == '&&':
            return And(left, right)
        elif op == '||':
            return Or(left, right)
        else:
            raise NotImplementedError(f"Operator {op} not supported")
    
    def visit_UnaryOp(self, node):
        """Handle unary operations like !, -, etc."""
        expr = self.visit(node.expr)
        
        if node.op == '!':
            return Not(expr)
        elif node.op == '-':
            return -expr
        elif node.op == '+':
            return expr
        else:
            raise NotImplementedError(f"Unary operator {node.op} not supported")
    
    def visit_ID(self, node):
        """Handle variable identifiers."""
        return self.get_or_create_var(node.name)
    
    def visit_Constant(self, node):
        """Handle constant values."""
        # Try to parse as int, handle long long casting
        value_str = node.value
        if value_str.startswith('0x'):
            return int(value_str, 16)
        else:
            return int(value_str)
    
    def visit_Cast(self, node):
        """Handle type casts like (long long)x."""
        # For equivalence checking, we can mostly ignore casts
        # since we're using unbounded Ints
        # The cast has an 'expr' attribute that contains the expression being cast
        if hasattr(node, 'expr'):
            return self.visit(node.expr)
        else:
            # Fallback for unexpected structure
            return self.generic_visit(node)
    
    def visit_FuncCall(self, node):
        """Handle function calls (rare in predicates)."""
        raise NotImplementedError("Function calls not supported in predicates")
    
    def visit_ArrayRef(self, node):
        """Handle array references like a[i]."""
        # Represent as a Z3 function: Array(name, IntSort(), IntSort())
        array_name = node.name.name if hasattr(node.name, 'name') else str(node.name)
        index = self.visit(node.subscript)
        
        # Get or create array
        if array_name not in self.variables:
            self.variables[array_name] = Array(array_name, IntSort(), IntSort())
        
        return Select(self.variables[array_name], index)
    
    def generic_visit(self, node):
        """Recursively visit children."""
        for child in node:
            result = self.visit(child)
            if result is not None:
                return result
        return None


def parse_c_predicate_to_z3(predicate_str: str):
    """
    Parse a C predicate string into a Z3 expression.
    
    Args:
        predicate_str: C boolean expression (e.g., "x + y == 10 && z > 0")
    
    Returns:
        tuple: (z3_expression, dict of variables used)
    """
    # Wrap in a function to make it valid C
    c_code = f"void dummy() {{ assert({predicate_str}); }}"
    
    try:
        parser = pycparser.c_parser.CParser()
        ast = parser.parse(c_code)
        
        # Find the assert statement - assert is parsed as a FuncCall
        statement = ast.ext[0].body.block_items[0]
        
        # Extract the actual predicate from assert's argument
        if isinstance(statement, c_ast.FuncCall) and hasattr(statement, 'args') and statement.args:
            # assert(predicate) - get the first (and only) argument
            predicate_expr = statement.args.exprs[0]
        else:
            # Fallback if structure is different
            predicate_expr = statement
        
        # Convert to Z3
        converter = CToZ3Converter()
        z3_expr = converter.visit(predicate_expr)
        
        return z3_expr, converter.variables
    except Exception as e:
        import traceback
        traceback.print_exc()  # Debug: print full traceback
        raise ValueError(f"Failed to parse predicate '{predicate_str}': {e}")


def check_semantic_equivalence(pred1: str, pred2: str) -> bool:
    """
    Check if two C predicates are logically equivalent using Z3.
    Fully agnostic - no need to specify variables or types.
    
    Args:
        pred1: First C predicate (e.g., "q + a * b * p == x * y")
        pred2: Second C predicate (e.g., "a * b * p + q >= x * y && a * b * p + q <= x * y")
    
    Returns:
        True if pred1 ⟺ pred2, False otherwise or if parsing fails
    """
    try:
        # Parse both predicates
        z3_pred1, _ = parse_c_predicate_to_z3(pred1)
        z3_pred2, _ = parse_c_predicate_to_z3(pred2)
        
        # Create a solver
        solver = Solver()
        
        # Check if (pred1 ⟺ pred2) is a tautology
        # by checking if ¬(pred1 ⟺ pred2) is UNSAT
        solver.add(Not(z3_pred1 == z3_pred2))
        
        result = solver.check()
        
        if result == unsat:
            return True  # Equivalent
        elif result == sat:
            # Not equivalent - we can even get a counterexample
            model = solver.model()
            print(f"Counterexample: {model}")
            return False
        else:  # unknown
            return False
            
    except Exception as e:
        print(f"Warning: Equivalence check failed: {e}")
        return False


# Example usage
if __name__ == "__main__":
    # Test case from your problem
    pred1 = "q + a * b * p == (long long)x * y"
    pred2 = "a * b * p + q <= (long long)x * y && a * b * p + q >= (long long)x * y"
    
    result = check_semantic_equivalence(pred1, pred2)
    print(f"Are predicates equivalent? {result}")  # Should print True
    
    # Another test
    pred3 = "x > 0 && y > 0"
    pred4 = "y > 0 && x > 0"
    print(f"Commutativity test: {check_semantic_equivalence(pred3, pred4)}")  # True
    
    # Non-equivalent test
    pred5 = "x > 0"
    pred6 = "x >= 0"
    print(f"Non-equivalent test: {check_semantic_equivalence(pred5, pred6)}")  # False


def check_syntactic_equivalence(c1, c2):
    """
    Check if two C predicates are syntactically equivalent by comparing ASTs.
    
    This is a syntactic check (same structure) rather than semantic (logical equivalence).
    Use check_semantic_equivalence() for logical equivalence checking.
    
    Args:
        c1: First C predicate string
        c2: Second C predicate string
    
    Returns:
        True if the ASTs are identical, False otherwise
    """
    # parse the statements into ASTs
    try:
        ast1 = pycparser.c_parser.CParser().parse("void main() {" + f"assert({c1});" + "}")
        ast2 = pycparser.c_parser.CParser().parse("void main() {" + f"assert({c2});" + "}")

        # Compare the ASTs recursively
        return compare_nodes(ast1, ast2)
    except Exception:
        return False


def compare_nodes(node1, node2):
    """
    Recursively compare two AST nodes for structural equality.
    
    Args:
        node1: First AST node
        node2: Second AST node
    
    Returns:
        True if nodes are structurally identical, False otherwise
    """
    # Check if both nodes are None
    if node1 is None and node2 is None:
        return True

    # Check if one node is None and the other is not
    if node1 is None or node2 is None:
        return False

    # Check if both nodes have the same class
    if type(node1) is not type(node2):  # Use 'is' for type identity comparison
        return False

    # Check if both nodes have the same attributes
    for attr in node1.attr_names:
        if getattr(node1, attr) != getattr(node2, attr):
            return False

    # Check if both nodes have the same number of children
    if len(node1.children()) != len(node2.children()):
        return False

    # Compare the children recursively
    for child1, child2 in zip(node1.children(), node2.children()):
        if not compare_nodes(child1[1], child2[1]):
            return False

    # If all checks passed, return True
    return True
