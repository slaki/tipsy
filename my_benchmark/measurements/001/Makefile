tipsy=/home/jenkins/tipsy16-new/tipsy
tipsy_lib=$(dir $(tipsy))lib
gen_pcap=$(tipsy_lib)/gen_pcap.py

results.json: traffic.pcap benchmark.json
	$(tipsy_lib)/run_measurement.py

pipeline.json: pipeline-in.json
	$(tipsy_lib)/gen_conf.py -j $^ -o $@

.DELETE_ON_ERROR:
traffic.pcap: traffic.json pipeline.json
	$(gen_pcap) --json traffic.json --conf pipeline.json --output $@
