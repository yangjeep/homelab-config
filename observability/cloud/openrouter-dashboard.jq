def tempo_panel($id; $title; $query; $unit; $x; $y; $type; $reduce):
  {id:$id,title:$title,type:$type,gridPos:{x:$x,y:$y,w:12,h:8},
   datasource:{type:"tempo",uid:"${DS_TEMPO}"},
   targets:[{refId:"A",datasource:{type:"tempo",uid:"${DS_TEMPO}"},
     queryType:"traceql",query:$query,tableType:"traces",limit:20,
     metricsQueryType:"range",step:"300s",exemplars:(if $type=="stat" then 0 else 3 end)}],
   fieldConfig:{defaults:{unit:$unit},overrides:[]},
   options:(if $type=="stat" then
     {reduceOptions:{calcs:[$reduce],fields:"/^(hermes|wallos|paperless-ngx|warp|dbeaver)$/",values:false},textMode:"auto",colorMode:"none",graphMode:"none"}
     else {legend:{displayMode:"table",placement:"bottom",calcs:[$reduce]},tooltip:{mode:"multi",sort:"desc"}}
     end)};
"{ resource.service.name = \"openrouter\" && span:name = \"LLM Generation\" }" as $calls |
"span.trace.metadata.openrouter.api_key_name" as $app |
{uid:"ai-openrouter-cloud",title:"AI - OpenRouter Applications",schemaVersion:40,
 version:1,tags:["homelab","openrouter","control-plane"],timezone:"browser",
 refresh:"5m",time:{from:"now-24h",to:"now"},editable:true,
 description:"Native OpenRouter Broadcast traces. Only LLM Generation spans count as requests; provider-attempt child spans are excluded from request/token/cost totals. Coverage starts when Broadcast was enabled. Missing traces are not proof of zero requests. Costs are emitted usage estimates, not an invoice. Privacy Mode is OFF by user request; raw content stays in Tempo, not this dashboard source. Cross-model fallback causality is not inferred from model selection.",
 links:[{title:"Local Homelab NOC",type:"link",url:"http://192.168.253.228:3000/d/homelab-noc/homelab-noc",targetBlank:true}],
 panels:[
  tempo_panel(1;"Requests by application (selected range)";$calls+" | count_over_time() by("+$app+")";"short";0;0;"stat";"sum"),
  tempo_panel(2;"Estimated cost by application (USD, selected range)";$calls+" | sum_over_time(span.gen_ai.usage.total_cost) by("+$app+")";"currencyUSD";12;0;"stat";"sum"),
  tempo_panel(3;"Request outcomes by application";$calls+" | count_over_time() by("+$app+", span:status)";"short";0;8;"timeseries";"sum"),
  (tempo_panel(4;"Generation latency P50 / P95";$calls+" | quantile_over_time(duration, .5, .95) by("+$app+") > 0";"s";12;8;"timeseries";"lastNotNull")
   +{description:"Approximate percentiles within each five-minute interval. Positive-duration points only: Tempo otherwise fills idle intervals with zero, which is not measured zero latency."}),
  tempo_panel(5;"Input tokens by application";$calls+" | sum_over_time(span.gen_ai.usage.input_tokens) by("+$app+")";"short";0;16;"stat";"sum"),
  tempo_panel(6;"Output tokens by application";$calls+" | sum_over_time(span.gen_ai.usage.output_tokens) by("+$app+")";"short";12;16;"stat";"sum"),
  tempo_panel(7;"Actual model usage";$calls+" | count_over_time() by(span.gen_ai.response.model)";"short";0;24;"timeseries";"sum"),
  tempo_panel(8;"Serving provider outcomes";$calls+" | count_over_time() by(span.trace.metadata.openrouter.provider_name, span:status)";"short";12;24;"timeseries";"sum"),
  (tempo_panel(9;"Mean first-token latency";$calls+" | avg_over_time(span.trace.metadata.openrouter.first_token_ms) by("+$app+")";"ms";0;32;"timeseries";"lastNotNull")
   +{description:"Observed first-token timing, averaged within each five-minute interval. The tenant returned no series for quantiles of this float attribute; generation-duration P50/P95 is shown separately."}),
  (tempo_panel(10;"Additional provider attempts";"{ resource.service.name = \"openrouter\" && span.span.metadata.attempt_index > 0 } | count_over_time() by(span.trace.metadata.openrouter.provider_name)";"short";12;32;"timeseries";"sum")
   +{description:"Counts zero-based attempt indices greater than 0, not affected requests or cross-model fallbacks. Multiple additional attempts may belong to one generation. No series means no matching observed attempts in this range."})
 ]}
