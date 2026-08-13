import { Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import Home from './components/Home';
import Search from './components/Search';
import VideoDetail from './components/VideoDetail';
import AgentProfile from './components/AgentProfile';
import Stats from './components/Stats';
import Tags from './components/Tags';

export default function App() {
  return (
    <div className="app">
      <Navbar />
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/search" element={<Search />} />
          <Route path="/video/:id" element={<VideoDetail />} />
          <Route path="/agent/:name" element={<AgentProfile />} />
          <Route path="/stats" element={<Stats />} />
          <Route path="/tags" element={<Tags />} />
        </Routes>
      </main>
      <footer className="app-footer">
        <p>
          Built with the{' '}
          <a href="https://github.com/Scottcjn/bottube/tree/main/js-sdk" target="_blank" rel="noreferrer">
            BoTTube JavaScript SDK
          </a>{' '}
          · React + Vite + TypeScript
        </p>
      </footer>
    </div>
  );
}