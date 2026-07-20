// GENERATED FILE. DO NOT EDIT BY HAND.
// Regenerate with: just gen-validator
// Compiled from traceformat/trace-format.schema.json — see
// scripts/gen-trace-validator.mjs and the hand-written sidecar
// traceValidator.gen.d.ts.
"use strict";
export const validateExchange = validate46;
const schema38 = {"type":"object","required":["type","seq","request","attempts"],"not":{"required":["response","malformed"],"$comment":"response (decoded) and malformed (undecodable) are mutually exclusive; both absent means every attempt timed out"},"properties":{"type":{"const":"exchange"},"seq":{"type":"integer","minimum":1},"request":{"type":"object","required":["pdu","request_id","oids"],"properties":{"pdu":{"enum":["get","getnext","getbulk","discovery"]},"request_id":{"type":"integer"},"oids":{"type":"array","minItems":0,"items":{"$ref":"#/$defs/oid"}},"non_repeaters":{"type":"integer","minimum":0},"max_repetitions":{"type":"integer","minimum":0}},"if":{"properties":{"pdu":{"const":"getbulk"}}},"then":{"required":["non_repeaters","max_repetitions"]}},"attempts":{"type":"array","minItems":1,"items":{"type":"object","required":["sent_at","received_at"],"properties":{"sent_at":{"$ref":"#/$defs/reltime"},"received_at":{"oneOf":[{"$ref":"#/$defs/reltime"},{"type":"null"}]},"error":{"type":"string","description":"Open enum; socket-level error instead of silence. Known: icmp-port-unreachable, icmp-host-unreachable, send-failed. When set, received_at is null."}},"if":{"required":["error"]},"then":{"properties":{"received_at":{"type":"null"}}}}},"response":{"type":"object","required":["request_id","error_status","error_index","varbinds"],"properties":{"request_id":{"type":"integer","description":"As returned by the device; compare with request.request_id"},"error_status":{"type":"integer"},"error_index":{"type":"integer"},"varbinds":{"type":"array","items":{"$ref":"#/$defs/varbind"}}}},"stray_responses":{"type":"array","items":{"type":"object","required":["received_at"],"properties":{"received_at":{"$ref":"#/$defs/reltime"}}}},"violations":{"type":"array","items":{"type":"string","description":"Open enum; known: request-id-mismatch, oid-not-increasing, missing-end-of-mib, duplicate-response, malformed-ber, response-from-unexpected-source"}},"malformed":{"type":"object","required":["error"],"properties":{"error":{"type":"string"},"length":{"type":"integer","minimum":0,"description":"Datagram size in bytes (the bytes themselves are not stored)"},"salvaged":{"type":"object"}}}}};
const schema34 = {"type":"string","pattern":"^[0-9]+(\\.[0-9]+)*$"};
const schema37 = {"type":"number","minimum":0,"description":"Seconds since walk start, monotonic clock, microsecond precision"};
const pattern4 = new RegExp("^[0-9]+(\\.[0-9]+)*$", "u");
const schema42 = {"type":"object","required":["oid","vtype","vlen"],"properties":{"oid":{"$ref":"#/$defs/oid"},"vtype":{"type":"string","description":"Known: Integer, OctetString, Null, ObjectIdentifier, IpAddress, Counter32, Gauge32, TimeTicks, Opaque, Counter64, NoSuchObject, NoSuchInstance, EndOfMibView; unknown BER tags as tag:0xNN"},"vlen":{"type":"integer","minimum":0}}};

function validate27(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate27.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.oid === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "oid"},message:"must have required property '"+"oid"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.vtype === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "vtype"},message:"must have required property '"+"vtype"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.vlen === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "vlen"},message:"must have required property '"+"vlen"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.oid !== undefined){
let data0 = data.oid;
if(typeof data0 === "string"){
if(!pattern4.test(data0)){
const err3 = {instancePath:instancePath+"/oid",schemaPath:"#/$defs/oid/pattern",keyword:"pattern",params:{pattern: "^[0-9]+(\\.[0-9]+)*$"},message:"must match pattern \""+"^[0-9]+(\\.[0-9]+)*$"+"\""};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
}
else {
const err4 = {instancePath:instancePath+"/oid",schemaPath:"#/$defs/oid/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
}
if(data.vtype !== undefined){
if(typeof data.vtype !== "string"){
const err5 = {instancePath:instancePath+"/vtype",schemaPath:"#/properties/vtype/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
}
if(data.vlen !== undefined){
let data2 = data.vlen;
if(!((typeof data2 == "number") && (!(data2 % 1) && !isNaN(data2)))){
const err6 = {instancePath:instancePath+"/vlen",schemaPath:"#/properties/vlen/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(typeof data2 == "number"){
if(data2 < 0 || isNaN(data2)){
const err7 = {instancePath:instancePath+"/vlen",schemaPath:"#/properties/vlen/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
}
}
else {
const err8 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
validate27.errors = vErrors;
return errors === 0;
}
validate27.evaluated = {"props":{"oid":true,"vtype":true,"vlen":true},"dynamicProps":false,"dynamicItems":false};


function validate46(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate46.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
const _errs1 = errors;
const _errs2 = errors;
if(errors === _errs2){
if(data && typeof data == "object" && !Array.isArray(data)){
let missing0;
if(((data.response === undefined) && (missing0 = "response")) || ((data.malformed === undefined) && (missing0 = "malformed"))){
const err0 = {};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
}
}
var valid0 = _errs2 === errors;
if(valid0){
const err1 = {instancePath,schemaPath:"#/not",keyword:"not",params:{},message:"must NOT be valid"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
else {
errors = _errs1;
if(vErrors !== null){
if(_errs1){
vErrors.length = _errs1;
}
else {
vErrors = null;
}
}
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.type === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.seq === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "seq"},message:"must have required property '"+"seq"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.request === undefined){
const err4 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "request"},message:"must have required property '"+"request"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.attempts === undefined){
const err5 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "attempts"},message:"must have required property '"+"attempts"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.type !== undefined){
if("exchange" !== data.type){
const err6 = {instancePath:instancePath+"/type",schemaPath:"#/properties/type/const",keyword:"const",params:{allowedValue: "exchange"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data.seq !== undefined){
let data1 = data.seq;
if(!((typeof data1 == "number") && (!(data1 % 1) && !isNaN(data1)))){
const err7 = {instancePath:instancePath+"/seq",schemaPath:"#/properties/seq/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(typeof data1 == "number"){
if(data1 < 1 || isNaN(data1)){
const err8 = {instancePath:instancePath+"/seq",schemaPath:"#/properties/seq/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
}
if(data.request !== undefined){
let data2 = data.request;
const _errs9 = errors;
let valid2 = true;
const _errs10 = errors;
if(data2 && typeof data2 == "object" && !Array.isArray(data2)){
if(data2.pdu !== undefined){
if("getbulk" !== data2.pdu){
const err9 = {};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
}
var _valid0 = _errs10 === errors;
errors = _errs9;
if(vErrors !== null){
if(_errs9){
vErrors.length = _errs9;
}
else {
vErrors = null;
}
}
if(_valid0){
const _errs12 = errors;
if(data2 && typeof data2 == "object" && !Array.isArray(data2)){
if(data2.non_repeaters === undefined){
const err10 = {instancePath:instancePath+"/request",schemaPath:"#/properties/request/then/required",keyword:"required",params:{missingProperty: "non_repeaters"},message:"must have required property '"+"non_repeaters"+"'"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
if(data2.max_repetitions === undefined){
const err11 = {instancePath:instancePath+"/request",schemaPath:"#/properties/request/then/required",keyword:"required",params:{missingProperty: "max_repetitions"},message:"must have required property '"+"max_repetitions"+"'"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
var _valid0 = _errs12 === errors;
valid2 = _valid0;
}
if(!valid2){
const err12 = {instancePath:instancePath+"/request",schemaPath:"#/properties/request/if",keyword:"if",params:{failingKeyword: "then"},message:"must match \"then\" schema"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(data2 && typeof data2 == "object" && !Array.isArray(data2)){
if(data2.pdu === undefined){
const err13 = {instancePath:instancePath+"/request",schemaPath:"#/properties/request/required",keyword:"required",params:{missingProperty: "pdu"},message:"must have required property '"+"pdu"+"'"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(data2.request_id === undefined){
const err14 = {instancePath:instancePath+"/request",schemaPath:"#/properties/request/required",keyword:"required",params:{missingProperty: "request_id"},message:"must have required property '"+"request_id"+"'"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
if(data2.oids === undefined){
const err15 = {instancePath:instancePath+"/request",schemaPath:"#/properties/request/required",keyword:"required",params:{missingProperty: "oids"},message:"must have required property '"+"oids"+"'"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
if(data2.pdu !== undefined){
let data4 = data2.pdu;
if(!((((data4 === "get") || (data4 === "getnext")) || (data4 === "getbulk")) || (data4 === "discovery"))){
const err16 = {instancePath:instancePath+"/request/pdu",schemaPath:"#/properties/request/properties/pdu/enum",keyword:"enum",params:{allowedValues: schema38.properties.request.properties.pdu.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
if(data2.request_id !== undefined){
let data5 = data2.request_id;
if(!((typeof data5 == "number") && (!(data5 % 1) && !isNaN(data5)))){
const err17 = {instancePath:instancePath+"/request/request_id",schemaPath:"#/properties/request/properties/request_id/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
if(data2.oids !== undefined){
let data6 = data2.oids;
if(Array.isArray(data6)){
if(data6.length < 0){
const err18 = {instancePath:instancePath+"/request/oids",schemaPath:"#/properties/request/properties/oids/minItems",keyword:"minItems",params:{limit: 0},message:"must NOT have fewer than 0 items"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
const len0 = data6.length;
for(let i0=0; i0<len0; i0++){
let data7 = data6[i0];
if(typeof data7 === "string"){
if(!pattern4.test(data7)){
const err19 = {instancePath:instancePath+"/request/oids/" + i0,schemaPath:"#/$defs/oid/pattern",keyword:"pattern",params:{pattern: "^[0-9]+(\\.[0-9]+)*$"},message:"must match pattern \""+"^[0-9]+(\\.[0-9]+)*$"+"\""};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
else {
const err20 = {instancePath:instancePath+"/request/oids/" + i0,schemaPath:"#/$defs/oid/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
}
}
else {
const err21 = {instancePath:instancePath+"/request/oids",schemaPath:"#/properties/request/properties/oids/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
}
if(data2.non_repeaters !== undefined){
let data8 = data2.non_repeaters;
if(!((typeof data8 == "number") && (!(data8 % 1) && !isNaN(data8)))){
const err22 = {instancePath:instancePath+"/request/non_repeaters",schemaPath:"#/properties/request/properties/non_repeaters/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
if(typeof data8 == "number"){
if(data8 < 0 || isNaN(data8)){
const err23 = {instancePath:instancePath+"/request/non_repeaters",schemaPath:"#/properties/request/properties/non_repeaters/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
}
if(data2.max_repetitions !== undefined){
let data9 = data2.max_repetitions;
if(!((typeof data9 == "number") && (!(data9 % 1) && !isNaN(data9)))){
const err24 = {instancePath:instancePath+"/request/max_repetitions",schemaPath:"#/properties/request/properties/max_repetitions/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
if(typeof data9 == "number"){
if(data9 < 0 || isNaN(data9)){
const err25 = {instancePath:instancePath+"/request/max_repetitions",schemaPath:"#/properties/request/properties/max_repetitions/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
}
}
}
else {
const err26 = {instancePath:instancePath+"/request",schemaPath:"#/properties/request/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
}
if(data.attempts !== undefined){
let data10 = data.attempts;
if(Array.isArray(data10)){
if(data10.length < 1){
const err27 = {instancePath:instancePath+"/attempts",schemaPath:"#/properties/attempts/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
const len1 = data10.length;
for(let i1=0; i1<len1; i1++){
let data11 = data10[i1];
const _errs29 = errors;
let valid10 = true;
const _errs30 = errors;
if(data11 && typeof data11 == "object" && !Array.isArray(data11)){
let missing1;
if((data11.error === undefined) && (missing1 = "error")){
const err28 = {};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
}
var _valid1 = _errs30 === errors;
errors = _errs29;
if(vErrors !== null){
if(_errs29){
vErrors.length = _errs29;
}
else {
vErrors = null;
}
}
if(_valid1){
const _errs31 = errors;
if(data11 && typeof data11 == "object" && !Array.isArray(data11)){
if(data11.received_at !== undefined){
if(data11.received_at !== null){
const err29 = {instancePath:instancePath+"/attempts/" + i1+"/received_at",schemaPath:"#/properties/attempts/items/then/properties/received_at/type",keyword:"type",params:{type: "null"},message:"must be null"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
}
}
var _valid1 = _errs31 === errors;
valid10 = _valid1;
if(valid10){
var props0 = {};
props0.received_at = true;
}
}
if(!valid10){
const err30 = {instancePath:instancePath+"/attempts/" + i1,schemaPath:"#/properties/attempts/items/if",keyword:"if",params:{failingKeyword: "then"},message:"must match \"then\" schema"};
if(vErrors === null){
vErrors = [err30];
}
else {
vErrors.push(err30);
}
errors++;
}
if(data11 && typeof data11 == "object" && !Array.isArray(data11)){
if(data11.sent_at === undefined){
const err31 = {instancePath:instancePath+"/attempts/" + i1,schemaPath:"#/properties/attempts/items/required",keyword:"required",params:{missingProperty: "sent_at"},message:"must have required property '"+"sent_at"+"'"};
if(vErrors === null){
vErrors = [err31];
}
else {
vErrors.push(err31);
}
errors++;
}
if(data11.received_at === undefined){
const err32 = {instancePath:instancePath+"/attempts/" + i1,schemaPath:"#/properties/attempts/items/required",keyword:"required",params:{missingProperty: "received_at"},message:"must have required property '"+"received_at"+"'"};
if(vErrors === null){
vErrors = [err32];
}
else {
vErrors.push(err32);
}
errors++;
}
if(props0 !== true){
props0 = props0 || {};
props0.sent_at = true;
props0.received_at = true;
props0.error = true;
}
if(data11.sent_at !== undefined){
let data13 = data11.sent_at;
if(typeof data13 == "number"){
if(data13 < 0 || isNaN(data13)){
const err33 = {instancePath:instancePath+"/attempts/" + i1+"/sent_at",schemaPath:"#/$defs/reltime/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err33];
}
else {
vErrors.push(err33);
}
errors++;
}
}
else {
const err34 = {instancePath:instancePath+"/attempts/" + i1+"/sent_at",schemaPath:"#/$defs/reltime/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err34];
}
else {
vErrors.push(err34);
}
errors++;
}
}
if(data11.received_at !== undefined){
let data14 = data11.received_at;
const _errs38 = errors;
let valid14 = false;
let passing0 = null;
const _errs39 = errors;
if(typeof data14 == "number"){
if(data14 < 0 || isNaN(data14)){
const err35 = {instancePath:instancePath+"/attempts/" + i1+"/received_at",schemaPath:"#/$defs/reltime/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err35];
}
else {
vErrors.push(err35);
}
errors++;
}
}
else {
const err36 = {instancePath:instancePath+"/attempts/" + i1+"/received_at",schemaPath:"#/$defs/reltime/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err36];
}
else {
vErrors.push(err36);
}
errors++;
}
var _valid2 = _errs39 === errors;
if(_valid2){
valid14 = true;
passing0 = 0;
}
const _errs42 = errors;
if(data14 !== null){
const err37 = {instancePath:instancePath+"/attempts/" + i1+"/received_at",schemaPath:"#/properties/attempts/items/properties/received_at/oneOf/1/type",keyword:"type",params:{type: "null"},message:"must be null"};
if(vErrors === null){
vErrors = [err37];
}
else {
vErrors.push(err37);
}
errors++;
}
var _valid2 = _errs42 === errors;
if(_valid2 && valid14){
valid14 = false;
passing0 = [passing0, 1];
}
else {
if(_valid2){
valid14 = true;
passing0 = 1;
}
}
if(!valid14){
const err38 = {instancePath:instancePath+"/attempts/" + i1+"/received_at",schemaPath:"#/properties/attempts/items/properties/received_at/oneOf",keyword:"oneOf",params:{passingSchemas: passing0},message:"must match exactly one schema in oneOf"};
if(vErrors === null){
vErrors = [err38];
}
else {
vErrors.push(err38);
}
errors++;
}
else {
errors = _errs38;
if(vErrors !== null){
if(_errs38){
vErrors.length = _errs38;
}
else {
vErrors = null;
}
}
}
}
if(data11.error !== undefined){
if(typeof data11.error !== "string"){
const err39 = {instancePath:instancePath+"/attempts/" + i1+"/error",schemaPath:"#/properties/attempts/items/properties/error/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err39];
}
else {
vErrors.push(err39);
}
errors++;
}
}
}
else {
const err40 = {instancePath:instancePath+"/attempts/" + i1,schemaPath:"#/properties/attempts/items/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err40];
}
else {
vErrors.push(err40);
}
errors++;
}
}
}
else {
const err41 = {instancePath:instancePath+"/attempts",schemaPath:"#/properties/attempts/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err41];
}
else {
vErrors.push(err41);
}
errors++;
}
}
if(data.response !== undefined){
let data16 = data.response;
if(data16 && typeof data16 == "object" && !Array.isArray(data16)){
if(data16.request_id === undefined){
const err42 = {instancePath:instancePath+"/response",schemaPath:"#/properties/response/required",keyword:"required",params:{missingProperty: "request_id"},message:"must have required property '"+"request_id"+"'"};
if(vErrors === null){
vErrors = [err42];
}
else {
vErrors.push(err42);
}
errors++;
}
if(data16.error_status === undefined){
const err43 = {instancePath:instancePath+"/response",schemaPath:"#/properties/response/required",keyword:"required",params:{missingProperty: "error_status"},message:"must have required property '"+"error_status"+"'"};
if(vErrors === null){
vErrors = [err43];
}
else {
vErrors.push(err43);
}
errors++;
}
if(data16.error_index === undefined){
const err44 = {instancePath:instancePath+"/response",schemaPath:"#/properties/response/required",keyword:"required",params:{missingProperty: "error_index"},message:"must have required property '"+"error_index"+"'"};
if(vErrors === null){
vErrors = [err44];
}
else {
vErrors.push(err44);
}
errors++;
}
if(data16.varbinds === undefined){
const err45 = {instancePath:instancePath+"/response",schemaPath:"#/properties/response/required",keyword:"required",params:{missingProperty: "varbinds"},message:"must have required property '"+"varbinds"+"'"};
if(vErrors === null){
vErrors = [err45];
}
else {
vErrors.push(err45);
}
errors++;
}
if(data16.request_id !== undefined){
let data17 = data16.request_id;
if(!((typeof data17 == "number") && (!(data17 % 1) && !isNaN(data17)))){
const err46 = {instancePath:instancePath+"/response/request_id",schemaPath:"#/properties/response/properties/request_id/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err46];
}
else {
vErrors.push(err46);
}
errors++;
}
}
if(data16.error_status !== undefined){
let data18 = data16.error_status;
if(!((typeof data18 == "number") && (!(data18 % 1) && !isNaN(data18)))){
const err47 = {instancePath:instancePath+"/response/error_status",schemaPath:"#/properties/response/properties/error_status/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err47];
}
else {
vErrors.push(err47);
}
errors++;
}
}
if(data16.error_index !== undefined){
let data19 = data16.error_index;
if(!((typeof data19 == "number") && (!(data19 % 1) && !isNaN(data19)))){
const err48 = {instancePath:instancePath+"/response/error_index",schemaPath:"#/properties/response/properties/error_index/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err48];
}
else {
vErrors.push(err48);
}
errors++;
}
}
if(data16.varbinds !== undefined){
let data20 = data16.varbinds;
if(Array.isArray(data20)){
const len2 = data20.length;
for(let i2=0; i2<len2; i2++){
if(!(validate27(data20[i2], {instancePath:instancePath+"/response/varbinds/" + i2,parentData:data20,parentDataProperty:i2,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate27.errors : vErrors.concat(validate27.errors);
errors = vErrors.length;
}
}
}
else {
const err49 = {instancePath:instancePath+"/response/varbinds",schemaPath:"#/properties/response/properties/varbinds/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err49];
}
else {
vErrors.push(err49);
}
errors++;
}
}
}
else {
const err50 = {instancePath:instancePath+"/response",schemaPath:"#/properties/response/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err50];
}
else {
vErrors.push(err50);
}
errors++;
}
}
if(data.stray_responses !== undefined){
let data22 = data.stray_responses;
if(Array.isArray(data22)){
const len3 = data22.length;
for(let i3=0; i3<len3; i3++){
let data23 = data22[i3];
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.received_at === undefined){
const err51 = {instancePath:instancePath+"/stray_responses/" + i3,schemaPath:"#/properties/stray_responses/items/required",keyword:"required",params:{missingProperty: "received_at"},message:"must have required property '"+"received_at"+"'"};
if(vErrors === null){
vErrors = [err51];
}
else {
vErrors.push(err51);
}
errors++;
}
if(data23.received_at !== undefined){
let data24 = data23.received_at;
if(typeof data24 == "number"){
if(data24 < 0 || isNaN(data24)){
const err52 = {instancePath:instancePath+"/stray_responses/" + i3+"/received_at",schemaPath:"#/$defs/reltime/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err52];
}
else {
vErrors.push(err52);
}
errors++;
}
}
else {
const err53 = {instancePath:instancePath+"/stray_responses/" + i3+"/received_at",schemaPath:"#/$defs/reltime/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err53];
}
else {
vErrors.push(err53);
}
errors++;
}
}
}
else {
const err54 = {instancePath:instancePath+"/stray_responses/" + i3,schemaPath:"#/properties/stray_responses/items/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err54];
}
else {
vErrors.push(err54);
}
errors++;
}
}
}
else {
const err55 = {instancePath:instancePath+"/stray_responses",schemaPath:"#/properties/stray_responses/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err55];
}
else {
vErrors.push(err55);
}
errors++;
}
}
if(data.violations !== undefined){
let data25 = data.violations;
if(Array.isArray(data25)){
const len4 = data25.length;
for(let i4=0; i4<len4; i4++){
if(typeof data25[i4] !== "string"){
const err56 = {instancePath:instancePath+"/violations/" + i4,schemaPath:"#/properties/violations/items/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err56];
}
else {
vErrors.push(err56);
}
errors++;
}
}
}
else {
const err57 = {instancePath:instancePath+"/violations",schemaPath:"#/properties/violations/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err57];
}
else {
vErrors.push(err57);
}
errors++;
}
}
if(data.malformed !== undefined){
let data27 = data.malformed;
if(data27 && typeof data27 == "object" && !Array.isArray(data27)){
if(data27.error === undefined){
const err58 = {instancePath:instancePath+"/malformed",schemaPath:"#/properties/malformed/required",keyword:"required",params:{missingProperty: "error"},message:"must have required property '"+"error"+"'"};
if(vErrors === null){
vErrors = [err58];
}
else {
vErrors.push(err58);
}
errors++;
}
if(data27.error !== undefined){
if(typeof data27.error !== "string"){
const err59 = {instancePath:instancePath+"/malformed/error",schemaPath:"#/properties/malformed/properties/error/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err59];
}
else {
vErrors.push(err59);
}
errors++;
}
}
if(data27.length !== undefined){
let data29 = data27.length;
if(!((typeof data29 == "number") && (!(data29 % 1) && !isNaN(data29)))){
const err60 = {instancePath:instancePath+"/malformed/length",schemaPath:"#/properties/malformed/properties/length/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err60];
}
else {
vErrors.push(err60);
}
errors++;
}
if(typeof data29 == "number"){
if(data29 < 0 || isNaN(data29)){
const err61 = {instancePath:instancePath+"/malformed/length",schemaPath:"#/properties/malformed/properties/length/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err61];
}
else {
vErrors.push(err61);
}
errors++;
}
}
}
if(data27.salvaged !== undefined){
let data30 = data27.salvaged;
if(!(data30 && typeof data30 == "object" && !Array.isArray(data30))){
const err62 = {instancePath:instancePath+"/malformed/salvaged",schemaPath:"#/properties/malformed/properties/salvaged/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err62];
}
else {
vErrors.push(err62);
}
errors++;
}
}
}
else {
const err63 = {instancePath:instancePath+"/malformed",schemaPath:"#/properties/malformed/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err63];
}
else {
vErrors.push(err63);
}
errors++;
}
}
}
else {
const err64 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err64];
}
else {
vErrors.push(err64);
}
errors++;
}
validate46.errors = vErrors;
return errors === 0;
}
validate46.evaluated = {"props":{"type":true,"seq":true,"request":true,"attempts":true,"response":true,"stray_responses":true,"violations":true,"malformed":true},"dynamicProps":false,"dynamicItems":false};

export const validateHeader = validate48;
const schema33 = {"type":"object","required":["type","format_version","tool","started_at","session","snmp","settings"],"properties":{"type":{"const":"header"},"format_version":{"const":1},"tool":{"type":"string"},"started_at":{"type":"string","format":"date-time","description":"ISO 8601 UTC; the only wall-clock time in the file"},"label":{"type":"string"},"session":{"type":"object","required":["id","run","runs_total"],"properties":{"id":{"type":"string","description":"Random UUID per walk invocation; shared by all files of a matrix run"},"run":{"type":"integer","minimum":1},"runs_total":{"type":"integer","minimum":1}}},"snmp":{"type":"object","required":["version"],"properties":{"version":{"enum":["1","2c","3"]}}},"settings":{"type":"object","required":["bulk_size","timeout_s","retries","start_oid"],"properties":{"bulk_size":{"type":"integer","minimum":0,"description":"0 means plain GetNext walk"},"timeout_s":{"type":"number","exclusiveMinimum":0},"retries":{"type":"integer","minimum":0},"start_oid":{"$ref":"#/$defs/oid"},"time_budget_s":{"type":"number","exclusiveMinimum":0},"resume_from":{"$ref":"#/$defs/oid","description":"Walk cursor continued from a previous run; start_oid remains the subtree bound"}}}}};

function validate48(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate48.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.type === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.format_version === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "format_version"},message:"must have required property '"+"format_version"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.tool === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "tool"},message:"must have required property '"+"tool"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.started_at === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "started_at"},message:"must have required property '"+"started_at"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.session === undefined){
const err4 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "session"},message:"must have required property '"+"session"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.snmp === undefined){
const err5 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "snmp"},message:"must have required property '"+"snmp"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.settings === undefined){
const err6 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "settings"},message:"must have required property '"+"settings"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(data.type !== undefined){
if("header" !== data.type){
const err7 = {instancePath:instancePath+"/type",schemaPath:"#/properties/type/const",keyword:"const",params:{allowedValue: "header"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data.format_version !== undefined){
if(1 !== data.format_version){
const err8 = {instancePath:instancePath+"/format_version",schemaPath:"#/properties/format_version/const",keyword:"const",params:{allowedValue: 1},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
if(data.tool !== undefined){
if(typeof data.tool !== "string"){
const err9 = {instancePath:instancePath+"/tool",schemaPath:"#/properties/tool/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
if(data.started_at !== undefined){
if(!(typeof data.started_at === "string")){
const err10 = {instancePath:instancePath+"/started_at",schemaPath:"#/properties/started_at/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
if(data.label !== undefined){
if(typeof data.label !== "string"){
const err11 = {instancePath:instancePath+"/label",schemaPath:"#/properties/label/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
if(data.session !== undefined){
let data5 = data.session;
if(data5 && typeof data5 == "object" && !Array.isArray(data5)){
if(data5.id === undefined){
const err12 = {instancePath:instancePath+"/session",schemaPath:"#/properties/session/required",keyword:"required",params:{missingProperty: "id"},message:"must have required property '"+"id"+"'"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
if(data5.run === undefined){
const err13 = {instancePath:instancePath+"/session",schemaPath:"#/properties/session/required",keyword:"required",params:{missingProperty: "run"},message:"must have required property '"+"run"+"'"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
if(data5.runs_total === undefined){
const err14 = {instancePath:instancePath+"/session",schemaPath:"#/properties/session/required",keyword:"required",params:{missingProperty: "runs_total"},message:"must have required property '"+"runs_total"+"'"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
if(data5.id !== undefined){
if(typeof data5.id !== "string"){
const err15 = {instancePath:instancePath+"/session/id",schemaPath:"#/properties/session/properties/id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
if(data5.run !== undefined){
let data7 = data5.run;
if(!((typeof data7 == "number") && (!(data7 % 1) && !isNaN(data7)))){
const err16 = {instancePath:instancePath+"/session/run",schemaPath:"#/properties/session/properties/run/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
if(typeof data7 == "number"){
if(data7 < 1 || isNaN(data7)){
const err17 = {instancePath:instancePath+"/session/run",schemaPath:"#/properties/session/properties/run/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
}
if(data5.runs_total !== undefined){
let data8 = data5.runs_total;
if(!((typeof data8 == "number") && (!(data8 % 1) && !isNaN(data8)))){
const err18 = {instancePath:instancePath+"/session/runs_total",schemaPath:"#/properties/session/properties/runs_total/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
if(typeof data8 == "number"){
if(data8 < 1 || isNaN(data8)){
const err19 = {instancePath:instancePath+"/session/runs_total",schemaPath:"#/properties/session/properties/runs_total/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
}
}
else {
const err20 = {instancePath:instancePath+"/session",schemaPath:"#/properties/session/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
}
if(data.snmp !== undefined){
let data9 = data.snmp;
if(data9 && typeof data9 == "object" && !Array.isArray(data9)){
if(data9.version === undefined){
const err21 = {instancePath:instancePath+"/snmp",schemaPath:"#/properties/snmp/required",keyword:"required",params:{missingProperty: "version"},message:"must have required property '"+"version"+"'"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
if(data9.version !== undefined){
let data10 = data9.version;
if(!(((data10 === "1") || (data10 === "2c")) || (data10 === "3"))){
const err22 = {instancePath:instancePath+"/snmp/version",schemaPath:"#/properties/snmp/properties/version/enum",keyword:"enum",params:{allowedValues: schema33.properties.snmp.properties.version.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
}
else {
const err23 = {instancePath:instancePath+"/snmp",schemaPath:"#/properties/snmp/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
}
if(data.settings !== undefined){
let data11 = data.settings;
if(data11 && typeof data11 == "object" && !Array.isArray(data11)){
if(data11.bulk_size === undefined){
const err24 = {instancePath:instancePath+"/settings",schemaPath:"#/properties/settings/required",keyword:"required",params:{missingProperty: "bulk_size"},message:"must have required property '"+"bulk_size"+"'"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
if(data11.timeout_s === undefined){
const err25 = {instancePath:instancePath+"/settings",schemaPath:"#/properties/settings/required",keyword:"required",params:{missingProperty: "timeout_s"},message:"must have required property '"+"timeout_s"+"'"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
if(data11.retries === undefined){
const err26 = {instancePath:instancePath+"/settings",schemaPath:"#/properties/settings/required",keyword:"required",params:{missingProperty: "retries"},message:"must have required property '"+"retries"+"'"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
if(data11.start_oid === undefined){
const err27 = {instancePath:instancePath+"/settings",schemaPath:"#/properties/settings/required",keyword:"required",params:{missingProperty: "start_oid"},message:"must have required property '"+"start_oid"+"'"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
if(data11.bulk_size !== undefined){
let data12 = data11.bulk_size;
if(!((typeof data12 == "number") && (!(data12 % 1) && !isNaN(data12)))){
const err28 = {instancePath:instancePath+"/settings/bulk_size",schemaPath:"#/properties/settings/properties/bulk_size/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
if(typeof data12 == "number"){
if(data12 < 0 || isNaN(data12)){
const err29 = {instancePath:instancePath+"/settings/bulk_size",schemaPath:"#/properties/settings/properties/bulk_size/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
}
}
if(data11.timeout_s !== undefined){
let data13 = data11.timeout_s;
if(typeof data13 == "number"){
if(data13 <= 0 || isNaN(data13)){
const err30 = {instancePath:instancePath+"/settings/timeout_s",schemaPath:"#/properties/settings/properties/timeout_s/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err30];
}
else {
vErrors.push(err30);
}
errors++;
}
}
else {
const err31 = {instancePath:instancePath+"/settings/timeout_s",schemaPath:"#/properties/settings/properties/timeout_s/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err31];
}
else {
vErrors.push(err31);
}
errors++;
}
}
if(data11.retries !== undefined){
let data14 = data11.retries;
if(!((typeof data14 == "number") && (!(data14 % 1) && !isNaN(data14)))){
const err32 = {instancePath:instancePath+"/settings/retries",schemaPath:"#/properties/settings/properties/retries/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err32];
}
else {
vErrors.push(err32);
}
errors++;
}
if(typeof data14 == "number"){
if(data14 < 0 || isNaN(data14)){
const err33 = {instancePath:instancePath+"/settings/retries",schemaPath:"#/properties/settings/properties/retries/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err33];
}
else {
vErrors.push(err33);
}
errors++;
}
}
}
if(data11.start_oid !== undefined){
let data15 = data11.start_oid;
if(typeof data15 === "string"){
if(!pattern4.test(data15)){
const err34 = {instancePath:instancePath+"/settings/start_oid",schemaPath:"#/$defs/oid/pattern",keyword:"pattern",params:{pattern: "^[0-9]+(\\.[0-9]+)*$"},message:"must match pattern \""+"^[0-9]+(\\.[0-9]+)*$"+"\""};
if(vErrors === null){
vErrors = [err34];
}
else {
vErrors.push(err34);
}
errors++;
}
}
else {
const err35 = {instancePath:instancePath+"/settings/start_oid",schemaPath:"#/$defs/oid/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err35];
}
else {
vErrors.push(err35);
}
errors++;
}
}
if(data11.time_budget_s !== undefined){
let data16 = data11.time_budget_s;
if(typeof data16 == "number"){
if(data16 <= 0 || isNaN(data16)){
const err36 = {instancePath:instancePath+"/settings/time_budget_s",schemaPath:"#/properties/settings/properties/time_budget_s/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err36];
}
else {
vErrors.push(err36);
}
errors++;
}
}
else {
const err37 = {instancePath:instancePath+"/settings/time_budget_s",schemaPath:"#/properties/settings/properties/time_budget_s/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err37];
}
else {
vErrors.push(err37);
}
errors++;
}
}
if(data11.resume_from !== undefined){
let data17 = data11.resume_from;
if(typeof data17 === "string"){
if(!pattern4.test(data17)){
const err38 = {instancePath:instancePath+"/settings/resume_from",schemaPath:"#/$defs/oid/pattern",keyword:"pattern",params:{pattern: "^[0-9]+(\\.[0-9]+)*$"},message:"must match pattern \""+"^[0-9]+(\\.[0-9]+)*$"+"\""};
if(vErrors === null){
vErrors = [err38];
}
else {
vErrors.push(err38);
}
errors++;
}
}
else {
const err39 = {instancePath:instancePath+"/settings/resume_from",schemaPath:"#/$defs/oid/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err39];
}
else {
vErrors.push(err39);
}
errors++;
}
}
}
else {
const err40 = {instancePath:instancePath+"/settings",schemaPath:"#/properties/settings/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err40];
}
else {
vErrors.push(err40);
}
errors++;
}
}
}
else {
const err41 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err41];
}
else {
vErrors.push(err41);
}
errors++;
}
validate48.errors = vErrors;
return errors === 0;
}
validate48.evaluated = {"props":{"type":true,"format_version":true,"tool":true,"started_at":true,"label":true,"session":true,"snmp":true,"settings":true},"dynamicProps":false,"dynamicItems":false};

export const validateSummary = validate49;
const schema47 = {"type":"object","required":["type","at","exchanges","oids_seen","end_reason","violation_counts"],"properties":{"type":{"const":"summary"},"at":{"$ref":"#/$defs/reltime"},"exchanges":{"type":"integer","minimum":0},"oids_seen":{"type":"integer","minimum":0},"end_reason":{"type":"string","description":"Open enum; known: completed, unresponsive, interrupted, time-budget-exceeded, oid-loop"},"violation_counts":{"type":"object","additionalProperties":{"type":"integer","minimum":0}}}};

function validate49(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate49.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.type === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.at === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "at"},message:"must have required property '"+"at"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.exchanges === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "exchanges"},message:"must have required property '"+"exchanges"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.oids_seen === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "oids_seen"},message:"must have required property '"+"oids_seen"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.end_reason === undefined){
const err4 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "end_reason"},message:"must have required property '"+"end_reason"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.violation_counts === undefined){
const err5 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "violation_counts"},message:"must have required property '"+"violation_counts"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.type !== undefined){
if("summary" !== data.type){
const err6 = {instancePath:instancePath+"/type",schemaPath:"#/properties/type/const",keyword:"const",params:{allowedValue: "summary"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data.at !== undefined){
let data1 = data.at;
if(typeof data1 == "number"){
if(data1 < 0 || isNaN(data1)){
const err7 = {instancePath:instancePath+"/at",schemaPath:"#/$defs/reltime/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
else {
const err8 = {instancePath:instancePath+"/at",schemaPath:"#/$defs/reltime/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
if(data.exchanges !== undefined){
let data2 = data.exchanges;
if(!((typeof data2 == "number") && (!(data2 % 1) && !isNaN(data2)))){
const err9 = {instancePath:instancePath+"/exchanges",schemaPath:"#/properties/exchanges/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
if(typeof data2 == "number"){
if(data2 < 0 || isNaN(data2)){
const err10 = {instancePath:instancePath+"/exchanges",schemaPath:"#/properties/exchanges/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
}
if(data.oids_seen !== undefined){
let data3 = data.oids_seen;
if(!((typeof data3 == "number") && (!(data3 % 1) && !isNaN(data3)))){
const err11 = {instancePath:instancePath+"/oids_seen",schemaPath:"#/properties/oids_seen/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
if(typeof data3 == "number"){
if(data3 < 0 || isNaN(data3)){
const err12 = {instancePath:instancePath+"/oids_seen",schemaPath:"#/properties/oids_seen/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
}
if(data.end_reason !== undefined){
if(typeof data.end_reason !== "string"){
const err13 = {instancePath:instancePath+"/end_reason",schemaPath:"#/properties/end_reason/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
if(data.violation_counts !== undefined){
let data5 = data.violation_counts;
if(data5 && typeof data5 == "object" && !Array.isArray(data5)){
for(const key0 in data5){
let data6 = data5[key0];
if(!((typeof data6 == "number") && (!(data6 % 1) && !isNaN(data6)))){
const err14 = {instancePath:instancePath+"/violation_counts/" + key0.replace(/~/g, "~0").replace(/\//g, "~1"),schemaPath:"#/properties/violation_counts/additionalProperties/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
if(typeof data6 == "number"){
if(data6 < 0 || isNaN(data6)){
const err15 = {instancePath:instancePath+"/violation_counts/" + key0.replace(/~/g, "~0").replace(/\//g, "~1"),schemaPath:"#/properties/violation_counts/additionalProperties/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
}
}
else {
const err16 = {instancePath:instancePath+"/violation_counts",schemaPath:"#/properties/violation_counts/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
}
else {
const err17 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
validate49.errors = vErrors;
return errors === 0;
}
validate49.evaluated = {"props":{"type":true,"at":true,"exchanges":true,"oids_seen":true,"end_reason":true,"violation_counts":true},"dynamicProps":false,"dynamicItems":false};

export const validateSystemInfo = validate50;
const schema36 = {"type":"object","required":["type","at","point","values"],"properties":{"type":{"const":"system_info"},"at":{"$ref":"#/$defs/reltime"},"point":{"enum":["start","end"]},"values":{"type":"object","propertyNames":{"pattern":"^[0-9]+(\\.[0-9]+)*$"},"additionalProperties":{"type":["string","integer"]}}}};

function validate50(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate50.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.type === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.at === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "at"},message:"must have required property '"+"at"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.point === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "point"},message:"must have required property '"+"point"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.values === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "values"},message:"must have required property '"+"values"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.type !== undefined){
if("system_info" !== data.type){
const err4 = {instancePath:instancePath+"/type",schemaPath:"#/properties/type/const",keyword:"const",params:{allowedValue: "system_info"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
}
if(data.at !== undefined){
let data1 = data.at;
if(typeof data1 == "number"){
if(data1 < 0 || isNaN(data1)){
const err5 = {instancePath:instancePath+"/at",schemaPath:"#/$defs/reltime/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
}
else {
const err6 = {instancePath:instancePath+"/at",schemaPath:"#/$defs/reltime/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
}
if(data.point !== undefined){
let data2 = data.point;
if(!((data2 === "start") || (data2 === "end"))){
const err7 = {instancePath:instancePath+"/point",schemaPath:"#/properties/point/enum",keyword:"enum",params:{allowedValues: schema36.properties.point.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
}
if(data.values !== undefined){
let data3 = data.values;
if(data3 && typeof data3 == "object" && !Array.isArray(data3)){
for(const key0 in data3){
const _errs8 = errors;
if(typeof key0 === "string"){
if(!pattern4.test(key0)){
const err8 = {instancePath:instancePath+"/values",schemaPath:"#/properties/values/propertyNames/pattern",keyword:"pattern",params:{pattern: "^[0-9]+(\\.[0-9]+)*$"},message:"must match pattern \""+"^[0-9]+(\\.[0-9]+)*$"+"\"",propertyName:key0};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
}
var valid2 = _errs8 === errors;
if(!valid2){
const err9 = {instancePath:instancePath+"/values",schemaPath:"#/properties/values/propertyNames",keyword:"propertyNames",params:{propertyName: key0},message:"property name must be valid"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
}
for(const key1 in data3){
let data4 = data3[key1];
if((typeof data4 !== "string") && (!((typeof data4 == "number") && (!(data4 % 1) && !isNaN(data4))))){
const err10 = {instancePath:instancePath+"/values/" + key1.replace(/~/g, "~0").replace(/\//g, "~1"),schemaPath:"#/properties/values/additionalProperties/type",keyword:"type",params:{type: schema36.properties.values.additionalProperties.type},message:"must be string,integer"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
}
}
else {
const err11 = {instancePath:instancePath+"/values",schemaPath:"#/properties/values/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
}
else {
const err12 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
validate50.errors = vErrors;
return errors === 0;
}
validate50.evaluated = {"props":{"type":true,"at":true,"point":true,"values":true},"dynamicProps":false,"dynamicItems":false};
