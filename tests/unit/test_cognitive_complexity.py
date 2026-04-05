"""Tests for cognitive complexity calculation."""
import pytest
from metrics.runner.frontend_collector import SonarCognitiveComplexityCollector


class TestCognitiveComplexity:
    """Test suite for cognitive complexity scoring."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.calc = SonarCognitiveComplexityCollector()

    def test_simple_if(self):
        """Test simple if statement."""
        code = """
        function withIf(x) {
            if (x > 0) {
                return x;
            }
            return 0;
        }
        """
        complexity = self.calc.calculate_javascript_complexity(code)
        assert complexity == 1, f"Expected 1, got {complexity}"

    def test_nested_if(self):
        """Test nested if statements."""
        code = """
        function nested(a, b) {
            if (a > 0) {
                if (b > 0) {
                    return a + b;
                }
            }
            return 0;
        }
        """
        complexity = self.calc.calculate_javascript_complexity(code)
        # Outer if: +1, inner if: +1 + nesting penalty (+1) = +2
        assert complexity == 3, f"Expected 3, got {complexity}"

    def test_if_else(self):
        """Test if-else statement."""
        code = """
        function withIfElse(x) {
            if (x > 0) {
                return x;
            } else {
                return -x;
            }
        }
        """
        complexity = self.calc.calculate_javascript_complexity(code)
        # if: +1, else: +1
        assert complexity == 2, f"Expected 2, got {complexity}"

    def test_simple_for_loop(self):
        """Test simple for loop."""
        code = """
        function withFor(arr) {
            for (let i = 0; i < arr.length; i++) {
                console.log(arr[i]);
            }
        }
        """
        complexity = self.calc.calculate_javascript_complexity(code)
        # for: +1
        assert complexity == 1, f"Expected 1, got {complexity}"

    def test_for_with_break(self):
        """Test for loop with break statement."""
        code = """
        function loopWithBreak(arr) {
            for (let i = 0; i < arr.length; i++) {
                if (arr[i] === 'target') {
                    break;
                }
            }
        }
        """
        complexity = self.calc.calculate_javascript_complexity(code)
        # for: +1, if: +1 + nesting (+1), break: +1
        assert complexity == 4, f"Expected 4, got {complexity}"

    def test_try_catch(self):
        """Test try-catch statement."""
        code = """
        function withTryCatch() {
            try {
                risky();
            } catch (e) {
                handle(e);
            }
        }
        """
        complexity = self.calc.calculate_javascript_complexity(code)
        # catch adds +1
        assert complexity == 1, f"Expected 1, got {complexity}"

    def test_switch_statement(self):
        """Test switch statement."""
        code = """
        function withSwitch(x) {
            switch (x) {
                case 1:
                    return 'one';
                case 2:
                    return 'two';
                default:
                    return 'other';
            }
        }
        """
        complexity = self.calc.calculate_javascript_complexity(code)
        # switch: +1, case 1: +1, case 2: +1
        assert complexity == 3, f"Expected 3, got {complexity}"

    def test_ternary_operator(self):
        """Test ternary operator."""
        code = """
        function withTernary(x) {
            return x > 0 ? x : -x;
        }
        """
        complexity = self.calc.calculate_javascript_complexity(code)
        # ternary: +1
        assert complexity == 1, f"Expected 1, got {complexity}"

    def test_while_loop(self):
        """Test while loop."""
        code = """
        function withWhile(x) {
            while (x > 0) {
                x--;
            }
            return x;
        }
        """
        complexity = self.calc.calculate_javascript_complexity(code)
        # while: +1
        assert complexity == 1, f"Expected 1, got {complexity}"

    def test_boolean_operators_in_condition(self):
        """Test AND/OR operators in if condition."""
        code = """
        function withBooleans(a, b, c) {
            if (a && b || c) {
                return true;
            }
            return false;
        }
        """
        complexity = self.calc.calculate_javascript_complexity(code)
        # if: +1, && and ||: +2
        assert complexity == 3, f"Expected 3, got {complexity}"

    def test_complex_nested_flow(self):
        """Test complex nested control flow."""
        code = """
        function complex(arr, target) {
            for (let i = 0; i < arr.length; i++) {
                if (arr[i] === target) {
                    return i;
                } else if (arr[i] > target) {
                    break;
                }
            }
            return -1;
        }
        """
        complexity = self.calc.calculate_javascript_complexity(code)
        # for: +1
        # if: +1 + nesting (+1) = +2
        # else if: +1 (no additional nesting for else if continuation)
        # break: +1
        # Total: 1 + 2 + 1 + 1 + 1 = 6
        assert complexity == 6, f"Expected 6, got {complexity}"

    def test_empty_function(self):
        """Test empty function has zero complexity."""
        code = """
        function empty() {
            return 0;
        }
        """
        complexity = self.calc.calculate_javascript_complexity(code)
        assert complexity == 0, f"Expected 0, got {complexity}"
