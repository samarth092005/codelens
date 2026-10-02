from app.services.code_intelligence.parser import composite_parser
from app.services.code_intelligence.parser.javascript_parser import JavaScriptParser
from app.services.code_intelligence.parser.python_parser import PythonParser
from app.services.code_intelligence.parser.typescript_parser import TypeScriptParser


def test_python_parser_symbols_and_calls():
    parser = PythonParser()
    code = b"""
import os
from app.tax import calculate_tax, TAX_RATE

class InvoiceService:
    def __init__(self, multiplier):
        self.multiplier = multiplier

    def process_invoice(self, amount):
        tax = calculate_tax(amount)
        total = self._calculate_discount(tax)
        return total

    def _calculate_discount(self, val):
        return val * self.multiplier

def standalone_helper(x):
    return x + 1
"""
    result = parser.parse(code, "app/invoice.py")

    assert result.status == "PARSED"
    assert result.language == "python"

    # Symbols check
    symbols_by_name = {s.name: s for s in result.symbols}
    assert "InvoiceService" in symbols_by_name
    assert symbols_by_name["InvoiceService"].symbol_type == "class"
    assert symbols_by_name["InvoiceService"].qualified_name == "InvoiceService"

    assert "__init__" in symbols_by_name
    assert symbols_by_name["__init__"].symbol_type == "method"
    assert symbols_by_name["__init__"].parent_name == "InvoiceService"
    assert symbols_by_name["__init__"].qualified_name == "InvoiceService.__init__"

    assert "process_invoice" in symbols_by_name
    assert symbols_by_name["process_invoice"].symbol_type == "method"
    assert symbols_by_name["process_invoice"].visibility == "public"

    assert "_calculate_discount" in symbols_by_name
    assert symbols_by_name["_calculate_discount"].visibility in ("protected", "private")

    assert "standalone_helper" in symbols_by_name
    assert symbols_by_name["standalone_helper"].symbol_type == "function"
    assert symbols_by_name["standalone_helper"].parent_name is None

    # Line numbers check
    for s in result.symbols:
        assert s.line_start <= s.line_end
        assert s.line_start > 0

    # Imports check
    import_modules = [i.imported_module for i in result.imports]
    assert "os" in import_modules
    assert "app.tax" in import_modules
    tax_import = next(i for i in result.imports if i.imported_module == "app.tax")
    assert "calculate_tax" in tax_import.imported_names

    # Calls check
    calls_by_callee = {c.callee_name: c for c in result.calls}
    assert "calculate_tax" in calls_by_callee
    assert calls_by_callee["calculate_tax"].caller_name == "InvoiceService.process_invoice"
    assert "self._calculate_discount" in calls_by_callee


def test_javascript_parser():
    parser = JavaScriptParser()
    code = b"""
import React from 'react';
import { calculateTax } from './tax';
const config = require('./config');

export class InvoiceCalculator {
    calculateTotal(amount) {
        const tax = calculateTax(amount);
        return amount + tax;
    }
}

export function formatCurrency(num) {
    return '$' + num;
}

const sendNotification = (msg) => {
    alert(msg);
};
"""
    result = parser.parse(code, "src/calculator.js")
    assert result.status == "PARSED"

    sym_names = [s.name for s in result.symbols]
    assert "InvoiceCalculator" in sym_names
    assert "calculateTotal" in sym_names
    assert "formatCurrency" in sym_names
    assert "sendNotification" in sym_names

    method_sym = next(s for s in result.symbols if s.name == "calculateTotal")
    assert method_sym.symbol_type == "method"
    assert method_sym.parent_name == "InvoiceCalculator"

    import_mods = [i.imported_module for i in result.imports]
    assert "react" in import_mods
    assert "./tax" in import_mods
    assert "./config" in import_mods

    call_callees = [c.callee_name for c in result.calls]
    assert "calculateTax" in call_callees
    assert "alert" in call_callees


def test_typescript_parser():
    parser = TypeScriptParser()
    code = b"""
import { User } from './user';

export class UserService {
    public getUserName(user: User): string {
        return user.name;
    }

    private validateId(id: number): boolean {
        return id > 0;
    }
}

export const createUserService = (): UserService => {
    return new UserService();
};
"""
    result = parser.parse(code, "src/user_service.ts")
    assert result.status == "PARSED"
    assert result.language == "typescript"

    sym_names = [s.name for s in result.symbols]
    assert "UserService" in sym_names
    assert "getUserName" in sym_names
    assert "validateId" in sym_names
    assert "createUserService" in sym_names

    validate_sym = next(s for s in result.symbols if s.name == "validateId")
    assert validate_sym.visibility == "private"


def test_composite_parser_malformed_code():
    # Tree-sitter is resilient and recovers from syntax errors
    malformed_py = b"def broken( x, , ): return"
    res = composite_parser.parse(malformed_py, "broken.py", "python")
    # Must not raise an exception; must return ParseResult
    assert res.language == "python"

    # Unsupported language
    unsupported_res = composite_parser.parse(b"hello world", "file.xyz", "unknown")
    assert unsupported_res.status == "UNSUPPORTED"
