import React from 'react';
import { createRoot } from 'react-dom/client';
import { ModuleRegistry, AllCommunityModule } from 'ag-grid-community';
import { ModuleRegistry as ChartsRegistry, AllCommunityModule as ChartsCommunity } from 'ag-charts-community';
import './styles.css';
import { TOKENS } from './tokens.js';
import { setMode } from './theme.js';
import App from './App.jsx';

ModuleRegistry.registerModules([AllCommunityModule]);

ChartsRegistry.registerModules([ChartsCommunity]);

// One source for colour: tokens.js feeds the CSS variables, the grid theme and the chart theme.
const vars = (t) => Object.entries(t).map(([k, v]) => `--${k}:${v};`).join('');
const style = document.createElement('style');
style.textContent = `:root{${vars(TOKENS.light)}}@media (prefers-color-scheme: dark){:root:not([data-theme='light']){${vars(TOKENS.dark)}}}:root[data-theme='dark']{${vars(TOKENS.dark)}}:root[data-theme='light']{${vars(TOKENS.light)}}`;
document.head.appendChild(style);

let initial = document.documentElement.dataset.theme;
if (!initial) initial = 'light';
setMode(initial);

createRoot(document.getElementById('root')).render(<App initialTheme={initial} />);
