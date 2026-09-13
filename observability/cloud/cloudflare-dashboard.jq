def query($ref):
 {refId:$ref,datasource:{type:"yesoreyeram-infinity-datasource",uid:"leaselab-cloudflare"},
  type:"json",source:"url",format:"table",parser:"jq-backend",url:"https://api.cloudflare.com/client/v4/graphql",
  url_options:{method:"POST",body_type:"raw",body_content_type:"application/json",
    data:({query:$graphql,variables:{account:"280e7379fc5d19bfd9b65ee682896dbe",start:"${__timeFrom:date:iso}",end:"${__timeTo:date:iso}"}}|tojson)},
  root_selector:"if ((.errors // []) | length) > 0 then error(\"Cloudflare Workers Analytics returned an error\") else [.data.viewer.accounts[0].workersInvocationsAdaptive[] | {worker:.dimensions.scriptName,environment:(if (.dimensions.scriptName|endswith(\"-preview\")) then \"preview\" else \"production\" end),status:.dimensions.status,requests:.sum.requests,errors:.sum.errors,subrequests:.sum.subrequests,cpu_ms_p50:(.quantiles.cpuTimeP50/1000),cpu_ms_p99:(.quantiles.cpuTimeP99/1000)}] end",
  columns:[{selector:"worker",text:"Worker",type:"string"},{selector:"environment",text:"Environment",type:"string"},
    {selector:"status",text:"Status",type:"string"},{selector:"requests",text:"Requests",type:"number"},
    {selector:"errors",text:"Errors",type:"number"},{selector:"subrequests",text:"Subrequests",type:"number"},
    {selector:"cpu_ms_p50",text:"CPU P50 (ms)",type:"number"},{selector:"cpu_ms_p99",text:"CPU P99 (ms)",type:"number"}]};
{uid:"leaselab-cloudflare-workers",title:"LeaseLab - Cloudflare Workers",schemaVersion:40,version:1,
 tags:["leaselab","cloudflare"],timezone:"browser",refresh:"5m",time:{from:"now-24h",to:"now"},editable:true,
 description:"Native Cloudflare Workers Analytics queried via Infinity, scoped to six actual LeaseLab Workers. Data covers the selected range. Workers with no invocations may have no row; absence is not a health verdict. CPU is converted from API microseconds to milliseconds and is not wall duration. No request content or full logs are ingested.",
 panels:[
  {id:1,title:"Worker requests, outcomes and CPU by environment",type:"table",gridPos:{x:0,y:0,w:24,h:12},
   datasource:{type:"yesoreyeram-infinity-datasource",uid:"leaselab-cloudflare"},targets:[query("A")],
   transformations:[{id:"organize",options:{indexByName:{Worker:0,Environment:1,Requests:2,Errors:3,Status:4,Subrequests:5,"CPU P50 (ms)":6,"CPU P99 (ms)":7}}}],
   fieldConfig:{defaults:{custom:{align:"auto",cellOptions:{type:"auto"}}},overrides:[
     {matcher:{id:"byName",options:"Worker"},properties:[{id:"custom.width",value:240}]},
     {matcher:{id:"byName",options:"Status"},properties:[{id:"custom.width",value:180}]}
   ]},
   options:{showHeader:true,cellHeight:"sm",sortBy:[{displayName:"Requests",desc:true}]}},
  {id:2,title:"Coverage",type:"text",gridPos:{x:0,y:12,w:24,h:4},options:{mode:"markdown",
   content:"Six Workers are included: API, Workflows and Email, each with production and preview variants. No row means no observed invocation in this time window, not confirmed availability. Website-zone WAF/CDN metrics are not included: the existing Free zones do not satisfy the official zone integration prerequisites."}}
 ]}
