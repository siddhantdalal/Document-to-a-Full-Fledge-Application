import { Route, Routes } from "react-router-dom";

import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { JobStatus } from "./pages/JobStatus";
import { NewJob } from "./pages/NewJob";

export function App() {
  return (
    <div className="flex min-h-screen flex-col bg-gradient-to-b from-slate-50 to-white text-slate-900 antialiased">
      <Header />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<NewJob />} />
          <Route path="/jobs/:id" element={<JobStatus />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}
