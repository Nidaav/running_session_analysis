import React, { useState, useMemo } from 'react';
import Calendar from 'react-calendar';
import 'react-calendar/dist/Calendar.css';

const Planning = () => {
  const [date, setDate] = useState(new Date());
  const [showPopup, setShowPopup] = useState(false);
  const [selectedWorkout, setSelectedWorkout] = useState(null);

  const formatDate = (d) => d.toISOString().slice(0, 10);

  const trainingSessions = useMemo(() => {
    const start = new Date();
    start.setDate(start.getDate());

    const workouts = [
      {
        workout: 'Easy endurance run (45–60min)',
        details: 'Steady pace, 60–70% Max Heart Rate.'
      },
      {
        workout: 'Interval session (14 × 400m)',
        details: 'Fast 400m at 90% MHR, with 200m jog recovery.'
      },
      {
        workout: 'Hill session (6 × 3min uphill)',
        details: 'Strong effort at 85–90% MHR. Jog down for recovery.'
      },
      {
        workout: 'Strength & conditioning (40min)',
        details: 'Focus on eccentric control, core stability and trail-specific strength.'
      },
      {
        workout: 'Rest day or active mobility',
        details: 'Optional light stretching or walk.'
      },
      {
        workout: 'Recovery run (30–40min)',
        details: 'Very easy pace, full conversational effort.'
      },
      {
        workout: 'Long run (1h20–1h40)',
        details: 'Aerobic, steady effort. Bring hydration & fuel.'
      },
      {
        workout: 'Tempo run (20min at controlled intensity)',
        details: 'Run at 80–85% MHR to build lactate threshold.'
      },
      {
        workout: 'Mixed trail session (50–70min)',
        details: 'Varied terrain, moderate effort, focus on running technique.'
      },
      {
        workout: 'Plyometrics & drills',
        details: 'Short session: strides, skips, hops, and agility work.'
      },
      {
        workout: 'Progressive run (45min)',
        details: 'Increase pace every 10–15min, finishing strong but controlled.'
      },
      {
        workout: 'Interval session (8 × 1000m)',
        details: 'Perform at 88–92% MHR with 2min jog recovery.'
      },
      {
        workout: 'Rest day or active mobility',
        details: 'Optional light stretching or walk.'
      },
      {
        workout: 'Trail fartlek (45–60min)',
        details: 'Alternate moderate and strong efforts based on terrain.'
      },
      {
        workout: 'Endurance + strides',
        details: '40min easy + 9 × 15s relaxed accelerations.'
      },
      {
        workout: 'Race pace rehearsal (4 × 6min)',
        details: 'Run close to target trail race intensity with controlled breathing.'
      },
    ];

    return workouts.map((w, i) => {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      return {
        ...w,
        date: formatDate(d)
      };
    });
  }, []);

  // --- Find session by date ---
  const findWorkout = (dateString) => {
    return trainingSessions.find((s) => s.date === dateString);
  };

  const handleDayClick = (clickedDate) => {
    setDate(clickedDate);

    const dateString = formatDate(clickedDate);
    const session = findWorkout(dateString);

    if (session) {
      setSelectedWorkout(session);
      setShowPopup(true);
    }
  };

  const tileContent = ({ date, view }) => {
    if (view === 'month') {
      const session = trainingSessions.find((s) => s.date === formatDate(date));

      if (session) {
        return (
          <div className="training-dot">
            <span className="training-label">{session.workout}</span>
          </div>
        );
      }
    }
    return null;
  };

  const tileClassName = ({ date, view }) => {
    if (view === 'month') {
      const dateString = formatDate(date);
      const hasSession = findWorkout(dateString);
      return hasSession ? 'has-workout' : '';
    }
  };

  return (
    <div className="page-container">
      <h1>Training Plan</h1>
      <h4>Here is a suggested training program that will help you achieve your goals.</h4>
      <h4>The first fortnight is available and free of charge. To access the rest of the plan, subscribe to our personalized support.</h4>

      <div className="calendar-container">
        <Calendar
          onChange={setDate}
          value={date}
          locale="en-US"
          view="month"
          showNumberOfWeeks={1}
          onClickDay={handleDayClick}
          tileContent={tileContent}
          tileClassName={tileClassName}
        />
      </div>

      {/* Popup */}
      {showPopup && selectedWorkout && (
        <>
          <div className="modal-overlay" onClick={() => setShowPopup(false)} />
          <div className="modal-content">
            <h2>{selectedWorkout.workout}</h2>
            <h4><strong>Date:</strong> {new Date(selectedWorkout.date).toLocaleDateString('en-US')}</h4>
            <h4>{selectedWorkout.details}</h4>
            <button onClick={() => setShowPopup(false)}>Close</button>
          </div>
        </>
      )}

      <h4>The proposed plan is for guidance only. It aims to improve your performance in short trail runs but does not take into account your specific physical characteristics, training load, lifestyle, or daily constraints.</h4>

      <h4>For a tailor-made plan and to discuss your goals with a coach, subscribe to our personalized support.</h4>

      <div className="button-container">
        <button className="training-plan-button">
          Become a premium customer
        </button>
      </div>
    </div>
  );
};

export default Planning;