import test from 'node:test';
import assert from 'node:assert/strict';
import {readTicket,decisionOptions} from '../web/journey-session.js';
test('journey recovery keeps only a valid opaque capability, not arbitrary stored state',()=>{
 const valid={id:'a'.repeat(32),token:'b'.repeat(43),trip:{private:'not a ticket'}};
 assert.deepEqual(readTicket({getItem:()=>JSON.stringify(valid)}),{id:valid.id,token:valid.token});
 assert.equal(readTicket({getItem:()=>'{bad'}),null);
 assert.equal(readTicket({getItem:()=>JSON.stringify({id:'../ops',token:valid.token})}),null);
 assert.equal(readTicket({getItem:()=>{throw Error('blocked storage');}}),null);
});
test('only pending journeys expose supported decision buttons',()=>{
 const data={journey:{status:'pending'},decision:{options:['keep','transit','shell','fewer']}};
 assert.deepEqual(decisionOptions(data),['keep','transit','fewer']);
 for(const status of ['running','failed','interrupted','completed'])assert.deepEqual(decisionOptions({...data,journey:{status}}),[]);
});
