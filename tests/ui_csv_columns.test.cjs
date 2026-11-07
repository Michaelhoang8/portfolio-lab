const test=require('node:test');
const assert=require('node:assert/strict');
const {readCSVHeaders}=require('../portfolio/static/csv_columns.js');

test('suggests trimmed CSV columns with BOM and CRLF',()=>{
  assert.deepEqual(readCSVHeaders('\uFEFF date ,category,amount\r\n2026-01-01,A,10'),['date','category','amount']);
});
test('respects commas, escaped quotes, and line breaks inside quoted headers',()=>{
  assert.deepEqual(readCSVHeaders('"Last, first","a""b","two\nlines"\n1,2,3'),['Last, first','a"b','two\nlines']);
});
test('does not suggest ambiguous or incomplete header rows',()=>{
  for(const source of ['', 'a,a\n1,2','a, \n1,2','"unfinished','"a"extra,b\n1,2']){
    assert.deepEqual(readCSVHeaders(source),[]);
  }
});
test('stops at the header and bounds work on very large fields',()=>{
  assert.deepEqual(readCSVHeaders('a,b\n"broken body'),['a','b']);
  assert.deepEqual(readCSVHeaders('x'.repeat(70000)),[]);
  assert.deepEqual(readCSVHeaders(Array.from({length:51},(_,i)=>'x'+i).join(',')),[]);
  assert.equal(readCSVHeaders(Array.from({length:50},(_,i)=>'x'+i).join(',')).length,50);
});
