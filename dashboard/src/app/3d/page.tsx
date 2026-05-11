'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import dynamic from 'next/dynamic';
import Sidebar from '@/components/hud/Sidebar';
import { api, formatUptime, type StatusResponse, type MemoryEvent, VectorWebSocket } from '@/lib/api';
import { useVectorStore } from '@/store/vectorStore';

const Scene = dynamic(() => import('@/components/three/VectorScene'), {
  ssr: false,
  loading: () => (
    <div style={{
      width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: '#000', color: '#00ffff', fontFamily: 'monospace', fontSize: 14
    }}>
      INITIALIZING 3D ENGINE...
    </div>
  ),
});

const styles = {
  page: {
    width: '100vw', height: '100vh', background: '#000', overflow: 'hidden', position: 'relative' as const,
  },
  sceneWrap: {
    position: 'absolute' as const, top: 0, left: 0, width: '100%', height: '100%', zIndex: 0,
  },
  overlay: {
    position: 'absolute' as const, top: 0, left: 240, width: 'calc(100% - 240px)', height: '100%',
    zIndex: 10, pointerEvents: 'none' as const, padding: 20,
    display: 'flex', flexDirection: 'column' as const, justifyContent: 'space-between',
  },
  header: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
  },
  title: {
    color: '#00ffff', fontFamily: '"Courier New", monospace', fontSize: 12,
    letterSpacing: '0.15em', textTransform: 'uppercase' as const,
    textShadow: '0 0 20px rgba(0,255,255,0.5)',
  },
  titleMain: {
    fontSize: 28, fontWeight: 700, marginBottom: 4, letterSpacing: '0.2em',
  },
  row: {
    display: 'flex', gap: 16, marginTop: 12,
  },
  statCard: {
    background: 'rgba(0,20,40,0.7)', border: '1px solid rgba(0,255,255,0.2)', borderRadius: 8,
    padding: '10px 16px', minWidth: 140, backdropFilter: 'blur(8px)',
    fontFamily: '"Courier New", monospace',
  },
  statLabel: {
    color: '#4488aa', fontSize: 9, letterSpacing: '0.12em', textTransform: 'uppercase' as const,
    marginBottom: 4,
  },
  statValue: {
    color: '#ffffff', fontSize: 16, fontWeight: 700,
  },
  statSub: {
    color: '#446688', fontSize: 9, marginTop: 2,
  },
  bottomBar: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end',
    paddingBottom: 20,
  },
  nodeLabel: {
    color: '#4488aa', fontSize: 9, fontFamily: '"Courier New", monospace',
    letterSpacing: '0.1em', textTransform: 'uppercase' as const,
    background: 'rgba(0,20,40,0.6)', padding: '4px 10px', borderRadius: 4,
    border: '1px solid rgba(0,255,255,0.15)',
  },
  controls: {
    color: '#336688', fontSize: 10, fontFamily: '"Courier New", monospace',
    background: 'rgba(0,20,40,0.5)', padding: '8px 14px', borderRadius: 6,
    border: '1px solid rgba(0,255,255,0.1)',
  },
  error: {
    position: 'absolute' as const, bottom: 80, left: '50%', transform: 'translateX(-50%)',
    color: '#ff4444', fontFamily: 'monospace', fontSize: 12,
    background: 'rgba(255,0,0,0.1)', padding: '8px 16px', borderRadius: 6,
    border: '1px solid rgba(255,0,0,0.3)', zIndex: 20,
  },
  memoryFeed: {
    fontFamily: '"Courier New", monospace', fontSize: 10, color: '#446688',
    maxHeight: 120, overflowY: 'auto' as const,
    background: 'rgba(0,20,40,0.5)', borderRadius: 6, border: '1px solid rgba(0,255,255,0.1)',
    padding: 8, width: 300,
    display: 'flex', flexDirection: 'column' as const, gap: 4,
  },
  memItem: {
    display: 'flex', gap: 8, padding: '2px 0', borderBottom: '1px solid rgba(0,255,255,0.05)',
  },
  memTime: { color: '#336688', width: 60, flexShrink: 0 },
  memType: { color: '#4488aa', width: 80, flexShrink: 0 },
  memText: { color: '#668899', overflow: 'hidden', textOverflow: 'ellipsis' as const, whiteSpace: 'nowrap' as const },
  version: {
    color: '#336644', fontSize: 9, fontFamily: '"Courier New", monospace',
  },
  cmdInput: {
    width: '100%', background: 'rgba(0,20,40,0.8)', border: '1px solid rgba(0,255,255,0.3)',
    borderRadius: 6, padding: '10px 14px', color: '#00ffff', fontSize: 13,
    fontFamily: '"Courier New", monospace', outline: 'none', marginTop: 8,
  },
  cmdSubmit: {
    marginTop: 8, background: 'rgba(0,255,255,0.15)', border: '1px solid rgba(0,255,255,0.4)',
    borderRadius: 6, padding: '8px 16px', color: '#00ffff', fontSize: 11,
    fontFamily: '"Courier New", monospace', cursor: 'pointer', textTransform: 'uppercase' as const,
    letterSpacing: '0.1em', transition: 'all 0.2s',
  },
  wsIndicator: {
    display: 'flex', alignItems: 'center', gap: 6, fontSize: 10, fontFamily: '"Courier New", monospace',
  },
  wsDot: (connected: boolean) => ({
    width: 6, height: 6, borderRadius: '50%', background: connected ? '#00ff88' : '#ff4444',
    boxShadow: `0 0 8px ${connected ? '#00ff88' : '#ff4444'}`,
  }),
};

export default function ThreeDPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [events, setEvents] = useState<MemoryEvent[]>([]);
  const [error, setError] = useState('');
  const [wsConnected, setWsConnected] = useState(false);
  const [commandText, setCommandText] = useState('');
  const [commandResponse, setCommandResponse] = useState('');
  const wsRef = useRef<VectorWebSocket | null>(null);

  const { setAgents, addEvent, setStatus: setStoreStatus, addCommandResponse } = useVectorStore();

  const load = useCallback(async () => {
    try {
      const [s, m] = await Promise.all([api.status(), api.memoryRecent(10)]);
      setStatus(s);
      setEvents(m.events);
      setStoreStatus(s);
      setError('');
    } catch {
      setError('BRAIN SERVER OFFLINE');
    }
  }, [setStoreStatus]);

  useEffect(() => {
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    const ws = new VectorWebSocket();
    wsRef.current = ws;

    ws.onConnect = () => setWsConnected(true);
    ws.onDisconnect = () => setWsConnected(false);
    ws.onStatus = (data) => {
      setStatus(data);
      setStoreStatus(data);
    };
    ws.onEvent = (event) => {
      addEvent(event);
      setEvents((prev) => [event, ...prev].slice(0, 20));
    };
    ws.onCommandResponse = (response) => {
      setCommandResponse(response.response || JSON.stringify(response, null, 2));
      addCommandResponse(response);
    };

    ws.connect();
    ws.subscribe('status');
    ws.subscribe('events');

    return () => {
      ws.disconnect();
    };
  }, [setStoreStatus, addEvent, addCommandResponse]);

  const handleCommand = useCallback(async () => {
    if (!commandText.trim()) return;
    try {
      const resp = await api.executeCommand(commandText);
      setCommandResponse(resp.response || JSON.stringify(resp, null, 2));
      setCommandText('');
    } catch (e) {
      setCommandResponse('COMMAND FAILED');
    }
  }, [commandText]);

  return (
    <div style={styles.page}>
      <Sidebar />

      {/* 3D Scene */}
      <div style={styles.sceneWrap}>
        <Scene />
      </div>

      {/* Overlay Content */}
      <div style={styles.overlay}>
        {/* Top: Title + Stats */}
        <div>
          <div style={styles.header}>
            <div style={styles.title}>
              <div style={styles.titleMain}>VECTOR</div>
              <div>COGNITIVE OPERATING SYSTEM // 3D NEURAL INTERFACE</div>
            </div>
          </div>

          <div style={styles.row}>
            <div style={styles.statCard}>
              <div style={styles.statLabel}>WS</div>
              <div style={styles.wsIndicator}>
                <div style={styles.wsDot(wsConnected)} />
                <span style={{ color: wsConnected ? '#00ff88' : '#ff4444' }}>
                  {wsConnected ? 'CONNECTED' : 'OFFLINE'}
                </span>
              </div>
              <div style={styles.statSub}>WEBSOCKET</div>
            </div>
            <div style={styles.statCard}>
              <div style={styles.statLabel}>Status</div>
              <div style={{ ...styles.statValue, color: status?.loop_running ? '#00ff88' : '#ffaa00' }}>
                {status ? (status.loop_running ? 'ONLINE' : 'IDLE') : '—'}
              </div>
              <div style={styles.statSub}>SYSTEM LOOP</div>
            </div>
            <div style={styles.statCard}>
              <div style={styles.statLabel}>Uptime</div>
              <div style={styles.statValue}>{status ? formatUptime(status.uptime_seconds) : '—'}</div>
              <div style={styles.statSub}>v{status?.vector_version ?? '—'}</div>
            </div>
            <div style={styles.statCard}>
              <div style={styles.statLabel}>Agents</div>
              <div style={styles.statValue}>{status?.agents.count?.toString() ?? '—'}</div>
              <div style={styles.statSub}>ACTIVE DISTRICTS</div>
            </div>
            <div style={styles.statCard}>
              <div style={styles.statLabel}>Memory</div>
              <div style={styles.statValue}>
                {typeof status?.memory?.episodic_count === 'number'
                  ? (status.memory.episodic_count as number).toLocaleString()
                  : '—'}
              </div>
              <div style={styles.statSub}>EPISODIC RECORDS</div>
            </div>
          </div>
        </div>

        {/* Error */}
        {error && <div style={styles.error}>{error}</div>}

        {/* Bottom: Memory Feed + Command Input */}
        <div style={styles.bottomBar}>
          <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end' }}>
            <div style={styles.memoryFeed}>
              <div style={{ color: '#00ffff', fontSize: 9, marginBottom: 4, letterSpacing: '0.12em' }}>
                LIVE MEMORY FEED
              </div>
              {events.length === 0 ? (
                <div style={{ color: '#336688' }}>AWAITING EVENTS...</div>
              ) : (
                events.slice(0, 6).map((ev, i) => (
                  <div key={i} style={styles.memItem}>
                    <span style={styles.memTime}>{ev.timestamp?.slice(11, 19) ?? '—'}</span>
                    <span style={styles.memType}>{ev.event_type?.slice(0, 12) ?? ''}</span>
                    <span style={styles.memText}>{ev.content?.slice(0, 50) ?? ''}</span>
                  </div>
                ))
              )}
            </div>

            <div style={{ width: 300, display: 'flex', flexDirection: 'column' }}>
              <div style={{ color: '#00ffff', fontSize: 9, marginBottom: 4, letterSpacing: '0.12em' }}>
                COMMAND INPUT
              </div>
              <input
                style={styles.cmdInput}
                placeholder="Enter command..."
                value={commandText}
                onChange={(e) => setCommandText(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCommand()}
              />
              <button style={styles.cmdSubmit} onClick={handleCommand}>
                EXECUTE
              </button>
              {commandResponse && (
                <div style={{ ...styles.memoryFeed, marginTop: 8, maxHeight: 100, color: '#00ff88' }}>
                  {commandResponse.slice(0, 200)}
                </div>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
            <div style={styles.controls}>
              DRAG TO ROTATE · SCROLL TO ZOOM · RIGHT-CLICK TO PAN
            </div>
            <div style={styles.nodeLabel}>
              {status?.agents.districts?.join(' · ')?.toUpperCase() || 'NO DISTRICTS'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
