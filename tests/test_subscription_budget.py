"""Budget-control wiring through loopback, with fake upstream only."""
import copy
import json
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from codex_flow.budget import ExecutionBudget
from codex_flow.subscription import SubscriptionGateway, RequestBudget, MAX_REQUEST_BYTES
import test_subscription as fixture


class Clock:
    now=0.
    def __call__(self):return self.now


def payload():
    return {'model':'gpt-6.1-sol','reasoning':{'effort':'xhigh'},
            'input':[{'role':'user','content':'Synthetic task; preserve this input'}],
            'tools':[{'type':'function','name':'tool','parameters':{}}]}


class BudgetGatewayTests(unittest.TestCase):
    call=fixture.SubscriptionTests.call

    def test_single_forwards_original_bytes_with_shared_deadline(self):
        opener=fixture.Opener()
        raw=b'{ "model":"gpt-6.1-sol", "reasoning":{"effort":"xhigh"}, "input":[{"role":"user","content":"test"}] }'
        with SubscriptionGateway(opener=opener,execution_budget=ExecutionBudget(10),guidance=False) as gateway:
            self.assertEqual(self.call(gateway,raw=raw)[0],200)
            record=gateway.summary()['requests'][0]
        self.assertEqual(opener.requests[0].data,raw)
        self.assertEqual(record['guidance_status'],'disabled')

    def test_current_budget_suffix_preserves_all_original_items_and_fields(self):
        clock=Clock();budget=ExecutionBudget(100,clock=clock);clock.now=50
        original=payload();before=copy.deepcopy(original);opener=fixture.Opener()
        with SubscriptionGateway(opener=opener,execution_budget=budget,guidance=True) as gateway:
            self.assertEqual(self.call(gateway,original)[0],200)
            record=gateway.summary()['requests'][0]
        forwarded=json.loads(opener.requests[0].data)
        self.assertEqual(original,before)
        self.assertEqual(forwarded['input'][:-1],original['input'])
        self.assertEqual({k:v for k,v in forwarded.items() if k!='input'}, {k:v for k,v in original.items() if k!='input'})
        self.assertEqual(record['guidance_status'],'applied')
        self.assertEqual(record['input_schema'],{'input_type':'array','item_types':{'message':1},'stateful_field_types':{}})
        self.assertNotIn('Synthetic task',json.dumps(record))
        self.assertEqual(record['execution_budget']['phase'],'stabilize')
        self.assertIn('Read-only workers',forwarded['input'][-1]['content'][0]['text'])

    def test_unknown_and_stateful_inputs_forward_original_bytes(self):
        for extra,reason in (({'input':'string'},'unsupported_input'),({'previous_response_id':'owned-id'},'stateful_input')):
            document=payload()|extra;raw=json.dumps(document).encode();opener=fixture.Opener()
            with self.subTest(reason=reason), SubscriptionGateway(opener=opener,execution_budget=ExecutionBudget(10),guidance=True) as gateway:
                self.assertEqual(self.call(gateway,raw=raw)[0],200)
                self.assertEqual(gateway.summary()['requests'][0]['guidance_status'],reason)
            self.assertEqual(opener.requests[0].data,raw)

    def test_native_developer_additional_tools_are_preserved_opaque(self):
        document=payload()
        tools={'type':'additional_tools','id':'synthetic-tools','role':'developer',
               'tools':[{'type':'function','name':'fixture','parameters':{'type':'object'}}]}
        document['input'].insert(0,tools)
        opener=fixture.Opener()
        with SubscriptionGateway(opener=opener,execution_budget=ExecutionBudget(10),guidance=True) as gateway:
            self.assertEqual(self.call(gateway,document)[0],200)
            record=gateway.summary()['requests'][0]
        forwarded=json.loads(opener.requests[0].data)
        self.assertEqual(forwarded['input'][:-1],document['input'])
        self.assertEqual(record['guidance_status'],'applied')
        self.assertEqual(record['input_schema']['item_types']['additional_tools'],1)
        self.assertNotIn('synthetic-tools',json.dumps(record))

    def test_unrecognized_additional_tools_shape_keeps_original_bytes(self):
        for change in ({'role':'user'},{'tools':['invalid']},{'id':None}):
            document=payload()
            document['input'].insert(0,{'type':'additional_tools','id':'fixture','role':'developer','tools':[]}|change)
            raw=json.dumps(document).encode();opener=fixture.Opener()
            with self.subTest(change=change),SubscriptionGateway(opener=opener,execution_budget=ExecutionBudget(10),guidance=True) as gateway:
                self.assertEqual(self.call(gateway,raw=raw)[0],200)
                self.assertEqual(gateway.summary()['requests'][0]['guidance_status'],'unsupported_input')
            self.assertEqual(opener.requests[0].data,raw)

    def test_note_size_limit_falls_back_to_original_bytes(self):
        document=payload();document['input'][0]['content']=''
        empty=json.dumps(document).encode()
        document['input'][0]['content']='x'*(MAX_REQUEST_BYTES-len(empty))
        raw=json.dumps(document).encode();self.assertEqual(len(raw),MAX_REQUEST_BYTES)
        opener=fixture.Opener()
        with SubscriptionGateway(opener=opener,execution_budget=ExecutionBudget(10),guidance=True) as gateway:
            self.assertEqual(self.call(gateway,raw=raw)[0],200)
            self.assertEqual(gateway.summary()['requests'][0]['guidance_status'],'size_limit')
        self.assertEqual(opener.requests[0].data,raw)

    def test_serialization_incompatibility_keeps_original_request_bytes(self):
        document=payload();document['input'][0]['content']='surrogate: \ud800'
        raw=json.dumps(document).encode('ascii');opener=fixture.Opener()
        with SubscriptionGateway(opener=opener,execution_budget=ExecutionBudget(10),guidance=True) as gateway:
            self.assertEqual(self.call(gateway,raw=raw)[0],200)
            self.assertEqual(gateway.summary()['requests'][0]['guidance_status'],'serialization_incompatible')
        self.assertEqual(opener.requests[0].data,raw)

    def test_expiry_and_cancel_refuse_before_reservation_and_upstream(self):
        for reason,status in (('deadline_exhausted',408),('cancelled',503)):
            clock=Clock();budget=ExecutionBudget(10,clock=clock);opener=fixture.Opener()
            cancel=threading.Event()
            if reason=='deadline_exhausted':clock.now=10
            else:cancel.set()
            with self.subTest(reason=reason),SubscriptionGateway(opener=opener,execution_budget=budget,cancel=cancel) as gateway:
                code,body=self.call(gateway)
                self.assertEqual((code,json.loads(body)['error']['type']),(status,reason))
                self.assertEqual(gateway.budget.used,0)
                self.assertEqual(gateway.summary()['control_rejections'],{reason:1})
            self.assertEqual(opener.requests,[])

    def test_expiry_after_reservation_still_prevents_upstream(self):
        clock=Clock();budget=ExecutionBudget(10,clock=clock);opener=fixture.Opener()
        with SubscriptionGateway(opener=opener,execution_budget=budget,guidance=True) as gateway:
            begin=gateway._begin
            def expire(*args):
                record=begin(*args);clock.now=10;return record
            gateway._begin=expire
            self.assertEqual(self.call(gateway,payload())[0],408)
            self.assertEqual(gateway.budget.used,1)
            self.assertEqual(gateway.summary()['requests'][0]['reason'],'deadline_exhausted')
        self.assertEqual(opener.requests,[])

    def test_open_timeout_clamped_to_current_remaining_time(self):
        clock=Clock();budget=ExecutionBudget(100,clock=clock);clock.now=93
        class Opener(fixture.Opener):
            def open(self,request,timeout):
                self.timeout=timeout
                return super().open(request,timeout)
        opener=Opener()
        with SubscriptionGateway(opener=opener,execution_budget=budget) as gateway:
            self.assertEqual(self.call(gateway,payload())[0],200)
            record=gateway.summary()['requests'][0]
            self.assertEqual(record['execution_budget']['requests_remaining'],79)
        self.assertEqual(opener.timeout,7)
        self.assertGreaterEqual(record['upstream_open_s'],0)
        self.assertGreaterEqual(record['upstream_body_read_s'],0)

    def test_exhausted_attempts_have_specific_reason_without_retry(self):
        opener=fixture.Opener()
        with SubscriptionGateway(opener=opener,budget=RequestBudget(1),execution_budget=ExecutionBudget(10,1)) as gateway:
            self.assertEqual(self.call(gateway,payload())[0],200)
            status,body=self.call(gateway,payload())
            self.assertEqual(status,429)
            self.assertEqual(json.loads(body)['error']['type'],'request_budget_exhausted')
            self.assertEqual(gateway.budget.used,1)
        self.assertEqual(len(opener.requests),1)


if __name__=='__main__':unittest.main()
