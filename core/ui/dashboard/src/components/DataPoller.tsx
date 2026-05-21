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
  const setSecurity = useVectorStore((s) => s.setSecurity)
  const setTasks = useVectorStore((s) => s.setTasks)
  const setCouncilHistory = useVectorStore((s) => s.setCouncilHistory)
  const setHealth = useVectorStore((s) => s.setHealth)
  const setTrainingData = useVectorStore((s) => s.setTrainingData)
  const setLoopStatus = useVectorStore((s) => s.setLoopStatus)
  const setScheduler = useVectorStore((s) => s.setScheduler)
  const setInference = useVectorStore((s) => s.setInference)
  const setEmail = useVectorStore((s) => s.setEmail)
  const setChannels = useVectorStore((s) => s.setChannels)
  const setProviders = useVectorStore((s) => s.setProviders)
  const setTools = useVectorStore((s) => s.setTools)
  const setNetwork = useVectorStore((s) => s.setNetwork)
  const setAudit = useVectorStore((s) => s.setAudit)
  const setMetering = useVectorStore((s) => s.setMetering)
  const setJupyter = useVectorStore((s) => s.setJupyter)
  const setSandbox = useVectorStore((s) => s.setSandbox)
  const setSensing = useVectorStore((s) => s.setSensing)
  const setMedia = useVectorStore((s) => s.setMedia)
  const setMining = useVectorStore((s) => s.setMining)
  const setMcp = useVectorStore((s) => s.setMcp)
  const setVideo = useVectorStore((s) => s.setVideo)
  const setScraper = useVectorStore((s) => s.setScraper)
  const setSeo = useVectorStore((s) => s.setSeo)
  const setOauth = useVectorStore((s) => s.setOauth)
  const setResearch = useVectorStore((s) => s.setResearch)
  const setMigration = useVectorStore((s) => s.setMigration)
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

    const pollSecurity = async () => {
      try { const data = await api.securityStatus(); if (mountedRef.current) setSecurity(data) } catch {}
    }
    const pollTasks = async () => {
      try { const data = await api.tasks(); if (mountedRef.current) setTasks(data) } catch {}
    }
    const pollCouncil = async () => {
      try { const data = await api.councilHistory(); if (mountedRef.current && data.sessions) setCouncilHistory(data.sessions) } catch {}
    }
    const pollHealth = async () => {
      try { const data = await api.health(); if (mountedRef.current) setHealth(data) } catch {}
    }
    const pollTraining = async () => {
      try { const data = await api.trainingData(); if (mountedRef.current) setTrainingData(data) } catch {}
    }
    const pollLoop = async () => { try { const d = await api.loopStatus(); if (mountedRef.current) setLoopStatus(d) } catch {} }
    const pollScheduler = async () => { try { const d = await api.schedulerJobs(); if (mountedRef.current) setScheduler(d) } catch {} }
    const pollInference = async () => { try { const d = await api.inferenceStats(); if (mountedRef.current) setInference(d) } catch {} }
    const pollEmail = async () => { try { const d = await api.emailRecent(); if (mountedRef.current) setEmail(d) } catch {} }
    const pollChannels = async () => { try { const d = await api.channelsStatus(); if (mountedRef.current) setChannels(d) } catch {} }
    const pollProviders = async () => { try { const d = await api.providerRoutes(); if (mountedRef.current) setProviders(d) } catch {} }
    const pollTools = async () => { try { const d = await api.toolsRegistry(); if (mountedRef.current) setTools(d) } catch {} }
    const pollNetwork = async () => { try { const d = await api.networkPeers(); if (mountedRef.current) setNetwork(d) } catch {} }
    const pollAudit = async () => { try { const d = await api.auditRecent(); if (mountedRef.current) setAudit(d) } catch {} }
    const pollMetering = async () => { try { const d = await api.meteringStatus(); if (mountedRef.current) setMetering(d) } catch {} }
    const pollJupyter = async () => { try { const d = await api.jupyterSessions(); if (mountedRef.current) setJupyter(d) } catch {} }
    const pollSandbox = async () => { try { const d = await api.sandboxStatus(); if (mountedRef.current) setSandbox(d) } catch {} }
    const pollSensing = async () => { try { const d = await api.sensingStatus(); if (mountedRef.current) setSensing(d) } catch {} }
    const pollMedia = async () => { try { const d = await api.mediaModels(); if (mountedRef.current) setMedia(d) } catch {} }
    const pollMining = async () => { try { const d = await api.miningStatus(); if (mountedRef.current) setMining(d) } catch {} }
    const pollMcp = async () => { try { const d = await api.mcpStatus(); if (mountedRef.current) setMcp(d) } catch {} }
    const pollVideo = async () => { try { const d = await api.videoCompositions(); if (mountedRef.current) setVideo(d) } catch {} }
    const pollScraper = async () => { try { const d = await api.scraperStatus(); if (mountedRef.current) setScraper(d) } catch {} }
    const pollSeo = async () => { try { const d = await api.seoStatus(); if (mountedRef.current) setSeo(d) } catch {} }
    const pollOauth = async () => { try { const d = await api.oauthIntegrations(); if (mountedRef.current) setOauth(d) } catch {} }
    const pollResearch = async () => { try { const d = await api.researchStatus(); if (mountedRef.current) setResearch(d) } catch {} }
    const pollMigration = async () => { try { const d = await api.migrationSources(); if (mountedRef.current) setMigration(d) } catch {} }

    pollStatus(); pollAgents(); pollSystem(); pollGoals(); pollEvents(); pollSecurity(); pollTasks(); pollCouncil(); pollHealth(); pollTraining(); pollLoop(); pollScheduler(); pollInference(); pollEmail(); pollChannels(); pollProviders(); pollTools(); pollNetwork(); pollAudit(); pollMetering(); pollJupyter(); pollSandbox(); pollSensing(); pollMedia(); pollMining(); pollMcp(); pollVideo(); pollScraper(); pollSeo(); pollOauth(); pollResearch(); pollMigration()

    const statusId = setInterval(pollStatus, 8000)
    const agentsId = setInterval(pollAgents, 8000)
    const systemId = setInterval(pollSystem, 4000)
    const goalsId = setInterval(pollGoals, 10000)
    const eventsId = setInterval(pollEvents, 6000)
    const securityId = setInterval(pollSecurity, 12000)
    const tasksId = setInterval(pollTasks, 15000)
    const councilId = setInterval(pollCouncil, 20000)
    const healthId = setInterval(pollHealth, 15000)
    const trainingId = setInterval(pollTraining, 30000)
    const loopId = setInterval(pollLoop, 8000)
    const schedulerId = setInterval(pollScheduler, 15000)
    const inferenceId = setInterval(pollInference, 12000)
    const emailId = setInterval(pollEmail, 20000)
    const channelsId = setInterval(pollChannels, 15000)
    const providersId = setInterval(pollProviders, 20000)
    const toolsId = setInterval(pollTools, 20000)
    const networkId = setInterval(pollNetwork, 25000)
    const auditId = setInterval(pollAudit, 20000)
    const meteringId = setInterval(pollMetering, 15000)
    const jupyterId = setInterval(pollJupyter, 20000)
    const sandboxId = setInterval(pollSandbox, 25000)
    const sensingId = setInterval(pollSensing, 15000)
    const mediaId = setInterval(pollMedia, 30000)
    const miningId = setInterval(pollMining, 20000)
    const mcpId = setInterval(pollMcp, 20000)
    const videoId = setInterval(pollVideo, 30000)
    const scraperId = setInterval(pollScraper, 20000)
    const seoId = setInterval(pollSeo, 30000)
    const oauthId = setInterval(pollOauth, 30000)
    const researchId = setInterval(pollResearch, 20000)
    const migrationId = setInterval(pollMigration, 30000)

    return () => {
      mountedRef.current = false
      clearInterval(statusId)
      clearInterval(agentsId)
      clearInterval(systemId)
      clearInterval(goalsId)
      clearInterval(eventsId)
      clearInterval(securityId)
      clearInterval(tasksId)
      clearInterval(councilId)
      clearInterval(healthId)
      clearInterval(trainingId)
      clearInterval(loopId)
      clearInterval(schedulerId)
      clearInterval(inferenceId)
      clearInterval(emailId)
      clearInterval(channelsId)
      clearInterval(providersId)
      clearInterval(toolsId)
      clearInterval(networkId)
      clearInterval(auditId)
      clearInterval(meteringId)
      clearInterval(jupyterId)
      clearInterval(sandboxId)
      clearInterval(sensingId)
      clearInterval(mediaId)
      clearInterval(miningId)
      clearInterval(mcpId)
      clearInterval(videoId)
      clearInterval(scraperId)
      clearInterval(seoId)
      clearInterval(oauthId)
      clearInterval(researchId)
      clearInterval(migrationId)
    }
  }, [])

  return null
}
