import { Route, Routes } from "react-router-dom";
import { JobStatus } from "./pages/JobStatus";
import { NewJob } from "./pages/NewJob";

export function App() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white text-slate-900 antialiased">
      <Routes>
        <Route path="/" element={<NewJob />} />
        <Route path="/jobs/:id" element={<JobStatus />} />
      </Routes>
    </div>
  );
}
