"""Generate the distributable template and structured-result schema contracts."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]/'packages/docuworks-integrations/docuworks_integrations'


def obj(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


def array(items, **kwargs): return dict(type='array', items=items, **kwargs)
def enum(*values): return dict(enum=list(values))
def nullable(value): return dict(anyOf=[value,dict(type='null')])
TEXT = dict(type='string')
NAME = dict(type='string', minLength=1, pattern=r'\S')
INT = dict(type='integer', minimum=1, maximum=2**31-1)
UUID = dict(type='string', pattern='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
HASH = dict(type='string', pattern='^[0-9a-f]{64}$')
TIME = dict(type='string', format='date-time')
BOOL = dict(type='boolean')
SIZE = dict(type='number', exclusiveMinimum=0)


def header(schema): return dict(schema=dict(const=schema), schema_version=dict(const='1.0'))


def template_schema():
    rect = obj(dict(rectangle_id=dict(type='string',pattern=r'^p[0-9]{4,}-a[0-9]{6,}$'),
                    annotation_order=INT, x=dict(type='number',minimum=0), y=dict(type='number',minimum=0),
                    width=SIZE,height=SIZE,purpose=enum('field','condition'),name=NAME,
                    expected=nullable(NAME),required=BOOL,output_order=nullable(INT),join=enum('連結','空白','改行')))
    rect['allOf'] = [
        {'if':{'properties':{'purpose':{'const':'field'}}}, 'then':{'properties':{'expected':{'type':'null'}}}},
        {'if':{'properties':{'purpose':{'const':'condition'}}}, 'then':{'properties':{'expected':NAME,'required':{'const':True},'output_order':{'type':'null'}}}}]
    page = obj(dict(page=INT,width_mm=SIZE,height_mm=SIZE,rotation=dict(const=0),rectangles=array(rect)))
    return obj(dict(**header('docuworks-rectangle-template'),template_id=UUID,name=NAME,created_at=TIME,
                    source_xdw_sha256=HASH,coordinate_basis=dict(const='reviewed'),
                    coordinate_system=dict(const='top-left-x-right-y-down'),unit=dict(const='mm'),pages=array(page,minItems=1)))


def manifest(schema, names):
    return obj(dict(**header(schema),status=dict(const='COMPLETE'),files=obj({name:HASH for name in sorted(names)})))


def write(name, schema):
    definition = {'$schema':'https://json-schema.org/draft/2020-12/schema','title':name,**schema}
    (ROOT/(name+'.schema.json')).write_bytes((json.dumps(definition,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))


def structured_schema():
    items = [json.loads((ROOT/f'reviewed-result-{v}.schema.json').read_text(encoding='utf-8'))[
        'properties']['pages']['items']['properties']['items']['items'] for v in ('1.0', '2.0')]
    source = obj(dict(result_id=UUID, page=INT, page_id=UUID, item=dict(oneOf=items)))
    entry = dict(rectangle_id=TEXT, name=NAME, page=INT, required=BOOL, value=nullable(TEXT),
                 status=enum('ok','missing','empty','unsupported'), diagnostics=array(TEXT),
                 sources=array({'$ref':'#/$defs/source'}))
    validation = obj(dict(mode=enum('identity','strict'),identity_checked=dict(const=True),page_structure_checked=BOOL))
    result = obj(dict(**header('docuworks-structured-result'),result_id=UUID,created_at=TIME,
        template=obj(dict(template_id=UUID,name=NAME,manifest_sha256=HASH,definition_sha256=HASH)),
        reviewed=obj(dict(result_id=UUID,schema_version=enum('1.0','2.0'),manifest_sha256=HASH,validation=validation)),
        applicable=BOOL,status=enum('ok','needs_review','not_applicable'),diagnostics=array(TEXT),
        conditions=array(obj(dict(**entry,expected=NAME,matched=BOOL))),fields=array(obj(entry))))
    result['$defs'] = dict(source=source)
    return result


def main():
    write('rectangle-template-1.0',template_schema())
    write('rectangle-template-manifest-1.0',manifest('docuworks-rectangle-template',{'template.json','source-template.xdw'}))
    write('structured-result-1.0',structured_schema())
    write('structured-result-manifest-1.0',manifest('docuworks-structured-result',{
        'structured.json','structured.jsonl','template.json','template-manifest.json',
        'reviewed.json','reviewed-manifest.json','identity.json','session.json'}))


if __name__ == '__main__': main()
