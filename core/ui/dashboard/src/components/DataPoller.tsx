import { useRef, useEffect } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { api } from '../lib/api'
import { mockStatus, mockAgents, mockSystemMetrics, mockGoals, mockEvents } from '../lib/mockData'
import { startTransition } from 'react'

export default function DataPoller() {
  const setStatus = useVectorStore((s) => s.setStatus)
  const setAgents = useVectorStore((s) => s.setAgents)
  const setSystemMetrics = useVectorStore((s) => s.setSystemMetrics)
  const setGoals = useVectorStore((s) => s.setGoals)
  const setEvents = useVectorStore((s) => s.setEvents)
  const mountedRef = useRef(true)
  const apiOk = useRef(true)

  const seedMock = () => {
    startTransition(() => {
      setStatus(mockStatus())
      setAgents(mockAgents())
      setSystemMetrics(mockSystemMetrics())
      setGoals(mockGoals())
      setEvents(mockEvents())
    })
  }

  useEffect(() => {
    mountedRef.current = true
    seedMock()

    const pollStatus = async () => {
      try {
        const data = await api.status()
        if (mountedRef.current) startTransition(() => setStatus(data))
        apiOk.current = true
      } catch {
        if (!apiOk.current && mountedRef.current) seedMock()
      }
    }

    const pollAgents = async () => {
      try {
        const data = await api.agents()
        if (mountedRef.current) startTransition(() => setAgents(data.agents))
      } catch {
        if (!apiOk.current && mountedRef.current) startTransition(() => setAgents(mockAgents()))
      }
    }

    const pollSystem = async () => {
      try {
        const data = await api.system()
        if (mountedRef.current) startTransition(() => setSystemMetrics(data))
      } catch {
        if (!apiOk.current && mountedRef.current) startTransition(() => setSystemMetrics(mockSystemMetrics()))
      }
    }

    const pollGoals = async () => {
      try {
        const data = await api.goals()
        if (mountedRef.current) startTransition(() => setGoals(data))
      } catch {
        if (!apiOk.current && mountedRef.current) startTransition(() => setGoals(mockGoals()))
      }
    }

    const pollEvents = async () => {
      try {
        const data = await api.memoryRecent(25)
        if (mountedRef.current) startTransition(() => setEvents(data.events))
      } catch {
        if (!apiOk.current && mountedRef.current) startTransition(() => setEvents(mockEvents()))
      }
    }

    pollStatus(); pollAgents(); pollSystem(); pollGoals(); pollEvents()

    const statusId = setInterval(pollStatus, 8000)
    const agentsId = setInterval(pollAgents, 8000)
    const systemId = setInterval(pollSystem, 4000)
    const goalsId = setInterval(pollGoals, 10000)
    const eventsId = setInterval(pollEvents, 6000)

    return () => {
      mountedRef.current = false
      clearInterval(statusId)
      clearInterval(agentsId)
      clearInterval(systemId)
      clearInterval(goalsId)
      clearInterval(eventsId)
    }
  }, [])

  return null
}
