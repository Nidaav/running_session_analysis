import React, { useMemo } from 'react';
import { useActivityData } from '../../hooks/useActivityData';
import { useNavigate } from 'react-router-dom';
// Charts pages
import MultiMetricChart from '../Charts/MultiMetricChart';
import MultiMetricChartByLap from '../Charts/MultiMetricChartByLap';
// Stats pages
import InterSeriesComparison  from '../Stats/InterSeriesComparison';
import PacingStrategy from '../Stats/PacingStrategy';
import RecoveryQuality from '../Stats/RecoveryQuality';
import StatsTableByRep from '../Stats/StatsTableByRep';


const Analysis = ({ csvText, csvByLapText }) => {
  const navigate = useNavigate();
  
  const handleViewPlan = () => {
    navigate('/tips');
  };

  const {
    activityData,
    filteredData,
    timeRange,
    setTimeRange
  } = useActivityData(csvText);


  if (!activityData) {
    return <div className="loading">Loading data...</div>;
  }

  return (
    <div className="page-container">
      <h1>Data Analysis</h1>
      <h2>The session studied is as follows: 2 × [8 × (200m at high intensity pace – 100m jog recovery)]</h2>

      {/* OVERALL PERFORMANCE ANALYSIS */}
      <div className="chart-container">
        <MultiMetricChart data={filteredData} timeRange={timeRange} onBrushChange={setTimeRange} />
      </div>

      <p>By segmenting the data from this session by lap, we will conduct an in-depth analysis of the various metrics collected.</p>

      {/* PERFORMANCE ANALYSIS BY LAPS */}
      <h2>Performance analysis by laps</h2>
      <div className="chart-container">
        <MultiMetricChartByLap csvByLapText={csvByLapText} timeRange={timeRange} onBrushChange={setTimeRange} />
      </div>
      
      {/* LAPS RECAP */}
      <p>The table below summarizes the key performance indicators for the intensity laps performed during the session and are classified into series (Serie 1 and Serie 2).</p>
      <StatsTableByRep csvByLapText={csvByLapText}/>

      {/* INTER-SERIES COMPARISON & GLOBAL DRIFTS */}
      <InterSeriesComparison csvByLapText={csvByLapText} />
      <p>The comparison between S1 and S2 highlights a clear progression in running efficiency. While cardiovascular demand increases markedly, the biomechanical indicators reveal a more effective and economical stride.</p>

      <p><strong>More specifically, S2 shows :</strong>
        <span style={{display: 'block'}}>A noticeable gain in speed, supported by higher cadence and improved ground reactivity.</span>
        <span style={{display: 'block'}}>A slightly longer stride, contributing to better forward propulsion.</span>
        <span style={{display: 'block'}}>An expected rise in heart rate, reflecting a stronger physiological investment to sustain performance.</span>
        <span style={{display: 'block'}}>A reduction in vertical ratio, indicating enhanced running economy and reduced vertical oscillation.</span>
      </p>
      
      {/* PACING STRATEGY */}
      <h2>Impact of Pacing Strategy on Heart Rate Response</h2>
      <p>The repetitions are classified into two main pace strategies based on the speed variance within a lap: <strong>Steady</strong> and <strong>Unsteady</strong> pace. These were classified using <strong>pacing drift (Δ%)</strong>, specifically its median (9.15). We then compared the induced cardiac stress (heart rate amplitude).</p>
      <PacingStrategy activityDataRaw={filteredData} activityDataByLap={csvByLapText}/>
      <p><strong>Pacing analysis:</strong> Contrary to expectations, the laps completed using a regular strategy performed less well. In fact, they were 0.16 km/h slower and, more importantly, resulted in an average increase of 7 bpm in heart rate amplitude per repetition.
        Irregular repetitions therefore seem to be more suitable for the athlete who completed this session. It is interesting to note that the ninth repetition was identified as “steady” and had a significant impact on the average “HR amplitude” as it occurred just after the inter-set recovery.
        Further analysis could be useful to determine which type of “unsteady” repetition is best suited to the athlete.</p>
      
      {/* RECOVERY QUALITY */}
      <h2>Recovery Quality Analysis (100m)</h2>
      <p>Recovery Quality is measured by the Heart Rate drop rate during the 100m recovery period. We also look for an overall cardiac drift by comparing the average heart rate at the end of the recovery phase between the two series.</p>
      <div className="chart-container">
        <RecoveryQuality activityDataRaw={filteredData} activityDataByLap={csvByLapText} />
      </div>
      <p><strong>Recovery Analysis:</strong> Recovery quality degrades in Series 2 (drop decreases from 40 to 25 bpm). The marked cardiac drift is significant: the average heart rate at the end of recovery increases by 20 bpm from S1 to S2. This signals a progressive overload of the cardiovascular system and a loss of efficiency in recovery, demonstrating the mounting physiological fatigue and good tolerance for lactic threshold work.</p>
      
     
      {/* KEY FINDINGS */}
      <div className="mt-10 bg-white shadow-xl rounded-xl p-6 border-t-4 border-blue-500">
        <h2 className="text-2xl font-bold text-gray-800 mb-4">Key Findings Summary</h2>
        <p>This session highlights an athlete capable of increasing his mechanical efficiency despite fatigue. Between the first and second sets, speed increases, cadence improves, and vertical ratio decreases: all indicators of a more economical and responsive stride. The correlations confirm this neuromuscular strength, with good contact time stability and better use of the stride at high intensity.</p>
        <p>At the same time, the main limitation is clearly cardiovascular. The drift in heart rate — both during repetitions and during recovery — becomes the determining factor in the deterioration of repeated performance. The strong link between poor recovery and an increase in HR_MAX in the next repetition confirms that the cardiac system, rather than mechanics, determines the quality of the effort.</p>
        <p>Finally, pacing analysis shows that a slightly irregular strategy seems to suit the athlete better, generating less cardiac stress while allowing for equivalent or even higher speeds.
          <span style={{display: 'block'}}> To summarize : mechanically very solid, physiologically under pressure. By optimizing recovery management and further developing the cardiac capacity to sustain work density, the athlete will be able to take even greater advantage of his excellent running efficiency.</span>  
        </p>      
      </div>

      <div className="button-container">
        <button onClick={handleViewPlan} className="training-plan-button">
          Check out the tips to improve
        </button>
      </div>
    </div>
    
  );
};

export default Analysis;