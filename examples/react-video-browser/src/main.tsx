import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { BottubeProvider } from './context/BottubeContext';
import App from './App';
import './App.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <BottubeProvider>
        <App />
      </BottubeProvider>
    </BrowserRouter>
  </React.StrictMode>,
);