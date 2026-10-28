"use client"

import { useState, useRef } from "react"
import { useQueryClient } from "@tanstack/react-query"
import {
  Sparkles,
  Loader2,
  Plus,
  Trash2,
  Calendar,
  Clock,
  User,
  AlertCircle,
  Pencil,
} from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Separator } from "@/components/ui/separator"
import { parseAgendaText, saveMeetingAgenda, ApiError } from "@/lib/api"
import type {
  Meeting,
  AgendaItem,
  ActionItem,
  AiSuggestionPayload,
} from "@/lib/types"

interface MeetingAgendaSectionProps {
  meeting: Meeting
  onUpdated?: (updated: Meeting) => void
}

export function MeetingAgendaSection({ meeting, onUpdated }: MeetingAgendaSectionProps) {
  const queryClient = useQueryClient()
  const [isEditing, setIsEditing] = useState<boolean>(!meeting.agenda)
  const [pasteText, setPasteText] = useState<string>("")
  const [isParsing, setIsParsing] = useState<boolean>(false)
  const [parseError, setParseError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState<boolean>(false)

  // Form values
  const [items, setItems] = useState<AgendaItem[]>(meeting.agenda?.items ?? [])
  const [actionItems, setActionItems] = useState<ActionItem[]>(
    meeting.agenda?.action_items ?? [],
  )

  // Track which fields were suggested by the model and remain untouched by user
  const [suggestedFields, setSuggestedFields] = useState<Set<string>>(new Set())

  // Keep original model suggestion payload for feedback quality tracking (Lab 6)
  const [aiSuggestion, setAiSuggestion] = useState<AiSuggestionPayload | null>(
    meeting.ai_suggestion ?? null,
  )

  const abortControllerRef = useRef<AbortController | null>(null)

  const handleCancelParse = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsParsing(false)
    toast.info("Agenda parsing cancelled")
  }

  const handleParse = async () => {
    const trimmed = pasteText.trim()
    if (!trimmed) {
      setParseError("Please paste some text first.")
      return
    }
    if (trimmed.length > 10000) {
      setParseError(`Text is too long (${trimmed.length} characters). Maximum allowed is 10,000 characters.`)
      return
    }

    setParseError(null)
    setIsParsing(true)

    const controller = new AbortController()
    abortControllerRef.current = controller

    try {
      const today = new Date().toISOString().split("T")[0]
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Kyiv"

      const response = await parseAgendaText(trimmed, today, tz, controller.signal)
      const parsed = response.agenda

      // Pre-fill agenda items
      const newItems: AgendaItem[] = (parsed.items ?? []).map((it) => ({
        topic: it.topic ?? "",
        owner: it.owner ?? "",
        minutes: it.minutes ?? null,
      }))

      // Pre-fill action items
      const newActionItems: ActionItem[] = (parsed.action_items ?? []).map((act) => ({
        task: act.task ?? "",
        owner: act.owner ?? "",
        due: act.due ?? null,
      }))

      // Record which fields were suggested by AI
      const initialSuggested = new Set<string>()
      newItems.forEach((it, idx) => {
        if (it.topic) initialSuggested.add(`item-${idx}-topic`)
        if (it.owner) initialSuggested.add(`item-${idx}-owner`)
        if (it.minutes !== null && it.minutes !== undefined) initialSuggested.add(`item-${idx}-minutes`)
      })
      newActionItems.forEach((act, idx) => {
        if (act.task) initialSuggested.add(`action-${idx}-task`)
        if (act.owner) initialSuggested.add(`action-${idx}-owner`)
        if (act.due) initialSuggested.add(`action-${idx}-due`)
      })

      setItems(newItems.length > 0 ? newItems : [{ topic: "", owner: "", minutes: null }])
      setActionItems(newActionItems)
      setSuggestedFields(initialSuggested)

      // Store model and prompt_version alongside suggestion
      setAiSuggestion({
        suggestion: parsed,
        model: response.model,
        prompt_version: response.prompt_version,
      })

      setIsEditing(true)
      toast.success("Agenda parsed! Review the suggested fields and save when ready.")
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return
      }
      if (err instanceof ApiError) {
        if (err.status === 413) {
          setParseError("The text is too long (over 10,000 characters). Please paste a shorter excerpt.")
        } else if (err.status === 429) {
          setParseError("The parsing service is currently busy. Please wait a few seconds and try again.")
        } else if (err.status === 422) {
          setParseError("The model could not find a clear meeting agenda in the text. You can fill out the form below by hand.")
        } else {
          setParseError(err.message || "Could not reach the agenda parser. Please check your network connection.")
        }
      } else {
        setParseError("An unexpected error occurred while parsing. You can enter the agenda manually.")
      }
    } finally {
      setIsParsing(false)
      abortControllerRef.current = null
    }
  }

  // Clear "suggested" mark when user edits a field
  const clearSuggested = (key: string) => {
    if (suggestedFields.has(key)) {
      setSuggestedFields((prev) => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
    }
  }

  const handleItemChange = (
    index: number,
    field: keyof AgendaItem,
    value: string | number | null,
  ) => {
    clearSuggested(`item-${index}-${field}`)
    setItems((prev) => {
      const updated = [...prev]
      updated[index] = { ...updated[index], [field]: value }
      return updated
    })
  }

  const handleActionItemChange = (
    index: number,
    field: keyof ActionItem,
    value: string | null,
  ) => {
    clearSuggested(`action-${index}-${field}`)
    setActionItems((prev) => {
      const updated = [...prev]
      updated[index] = { ...updated[index], [field]: value }
      return updated
    })
  }

  const addItem = () => {
    setItems((prev) => [...prev, { topic: "", owner: "", minutes: null }])
  }

  const removeItem = (index: number) => {
    setItems((prev) => prev.filter((_, i) => i !== index))
  }

  const addActionItem = () => {
    setActionItems((prev) => [...prev, { task: "", owner: "", due: null }])
  }

  const removeActionItem = (index: number) => {
    setActionItems((prev) => prev.filter((_, i) => i !== index))
  }

  const handleSave = async () => {
    const validItems = items.filter((it) => it.topic.trim().length > 0)
    if (validItems.length === 0) {
      toast.error("Please add at least one agenda topic.")
      return
    }

    setIsSaving(true)
    try {
      const updated = await saveMeetingAgenda(meeting.id, {
        items: validItems.map((it) => ({
          topic: it.topic.trim(),
          owner: it.owner?.trim() || null,
          minutes: it.minutes ? Number(it.minutes) : null,
        })),
        action_items: actionItems
          .filter((act) => act.task.trim().length > 0)
          .map((act) => ({
            task: act.task.trim(),
            owner: act.owner?.trim() || null,
            due: act.due || null,
          })),
        ai_suggestion: aiSuggestion,
      })

      queryClient.invalidateQueries({ queryKey: ["meetings"] })
      setIsEditing(false)
      onUpdated?.(updated)
      toast.success("Agenda saved successfully!")
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to save agenda"
      toast.error(message)
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <section className="space-y-4 pt-2">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-base font-semibold">
          <Clock className="size-4 text-purple-600" aria-hidden />
          Meeting Agenda
          {meeting.agenda && !isEditing ? (
            <Badge variant="outline" className="text-xs">
              {meeting.agenda.items.length} items
            </Badge>
          ) : null}
        </h3>

        {!isEditing && meeting.agenda ? (
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5 text-xs"
            onClick={() => setIsEditing(true)}
          >
            <Pencil className="size-3.5" />
            Edit Agenda
          </Button>
        ) : null}
      </div>

      {/* VIEW EXISTING SAVED AGENDA */}
      {!isEditing && meeting.agenda ? (
        <div className="space-y-4 rounded-xl border bg-card p-4 text-sm shadow-xs">
          <div className="space-y-2">
            <h4 className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
              Agenda Topics
            </h4>
            <ul className="space-y-2">
              {meeting.agenda.items.map((it, idx) => (
                <li
                  key={idx}
                  className="flex items-start justify-between rounded-lg border bg-muted/40 p-2.5 text-sm"
                >
                  <div className="space-y-0.5">
                    <p className="font-medium text-foreground">{it.topic}</p>
                    {it.owner ? (
                      <p className="flex items-center gap-1 text-xs text-muted-foreground">
                        <User className="size-3" />
                        {it.owner}
                      </p>
                    ) : null}
                  </div>
                  {it.minutes ? (
                    <Badge variant="secondary" className="text-xs font-mono">
                      {it.minutes} min
                    </Badge>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>

          {meeting.agenda.action_items && meeting.agenda.action_items.length > 0 ? (
            <>
              <Separator />
              <div className="space-y-2">
                <h4 className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                  Action Items
                </h4>
                <ul className="space-y-2">
                  {meeting.agenda.action_items.map((act, idx) => (
                    <li
                      key={idx}
                      className="flex items-start justify-between rounded-lg border bg-muted/20 p-2.5 text-sm"
                    >
                      <div className="space-y-0.5">
                        <p className="font-medium text-foreground">{act.task}</p>
                        {act.owner ? (
                          <p className="flex items-center gap-1 text-xs text-muted-foreground">
                            <User className="size-3" />
                            {act.owner}
                          </p>
                        ) : null}
                      </div>
                      {act.due ? (
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Calendar className="size-3" />
                          Due: {act.due}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            </>
          ) : null}
        </div>
      ) : null}

      {/* EDIT / PASTE FORM */}
      {isEditing ? (
        <div className="space-y-5 rounded-xl border bg-card p-4 text-sm shadow-xs">
          {/* PASTE AN AGENDA CARD */}
          <div className="rounded-lg border border-purple-100 bg-purple-50/40 p-3.5 space-y-3 dark:border-purple-900/40 dark:bg-purple-950/20">
            <div className="flex items-center justify-between">
              <label
                htmlFor="paste-agenda-text"
                className="flex items-center gap-1.5 text-xs font-semibold text-purple-900 dark:text-purple-300"
              >
                <Sparkles className="size-3.5 text-purple-600" />
                Paste an agenda (email, chat, notes)
              </label>
              <span className="text-[11px] text-muted-foreground">
                {pasteText.length} / 10,000 chars
              </span>
            </div>

            <Textarea
              id="paste-agenda-text"
              placeholder="e.g.: Пн 10:00, синч по прайсингу, 45 хв. 1) нові тарифи Pro — Олена, 15 хв 2) фідбек від клієнтів — Тарас..."
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
              disabled={isParsing}
              rows={3}
              className="resize-none bg-background text-xs leading-relaxed"
            />

            {parseError ? (
              <Alert variant="destructive" className="py-2 text-xs">
                <AlertCircle className="size-3.5" />
                <AlertTitle className="text-xs">Parsing issue</AlertTitle>
                <AlertDescription className="text-xs">{parseError}</AlertDescription>
              </Alert>
            ) : null}

            <div className="flex items-center gap-2">
              {isParsing ? (
                <>
                  <div className="flex items-center gap-2 text-xs text-purple-700 dark:text-purple-300">
                    <Loader2 className="size-4 animate-spin" />
                    <span>Parsing agenda with Claude... (~2-5s)</span>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={handleCancelParse}
                    className="ml-auto text-xs"
                  >
                    Cancel
                  </Button>
                </>
              ) : (
                <Button
                  type="button"
                  size="sm"
                  className="bg-purple-600 hover:bg-purple-700 text-white gap-1.5 text-xs"
                  onClick={handleParse}
                  disabled={!pasteText.trim()}
                >
                  <Sparkles className="size-3.5" />
                  Parse
                </Button>
              )}
            </div>
          </div>

          {/* AGENDA ITEMS FORM */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Agenda Topics
              </h4>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1 text-xs text-purple-600 hover:text-purple-700"
                onClick={addItem}
              >
                <Plus className="size-3.5" /> Add Topic
              </Button>
            </div>

            {items.map((item, idx) => (
              <div
                key={idx}
                className="space-y-2 rounded-lg border bg-background p-3 text-xs transition-colors"
              >
                <div className="flex items-start gap-2">
                  <div className="flex-1 space-y-1">
                    <div className="flex items-center gap-1.5">
                      <span className="font-semibold text-muted-foreground">#{idx + 1}</span>
                      <Input
                        placeholder="Topic title *"
                        value={item.topic}
                        onChange={(e) => handleItemChange(idx, "topic", e.target.value)}
                        className="h-8 text-xs font-medium"
                      />
                      {suggestedFields.has(`item-${idx}-topic`) ? (
                        <Badge
                          variant="secondary"
                          className="bg-purple-100 text-purple-700 text-[10px] px-1.5 py-0 h-5 dark:bg-purple-900/50 dark:text-purple-300"
                        >
                          suggested
                        </Badge>
                      ) : null}
                    </div>
                  </div>

                  {items.length > 1 ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-8 text-muted-foreground hover:text-destructive"
                      onClick={() => removeItem(idx)}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  ) : null}
                </div>

                <div className="grid grid-cols-2 gap-2 pl-6">
                  <div className="space-y-1">
                    <div className="flex items-center gap-1">
                      <Input
                        placeholder="Owner (optional)"
                        value={item.owner ?? ""}
                        onChange={(e) => handleItemChange(idx, "owner", e.target.value)}
                        className="h-7 text-xs"
                      />
                      {suggestedFields.has(`item-${idx}-owner`) ? (
                        <Badge
                          variant="secondary"
                          className="bg-purple-100 text-purple-700 text-[9px] px-1 py-0 h-4 dark:bg-purple-900/50 dark:text-purple-300"
                        >
                          suggested
                        </Badge>
                      ) : null}
                    </div>
                  </div>

                  <div className="space-y-1">
                    <div className="flex items-center gap-1">
                      <Input
                        type="number"
                        placeholder="Minutes"
                        min={1}
                        max={480}
                        value={item.minutes ?? ""}
                        onChange={(e) =>
                          handleItemChange(
                            idx,
                            "minutes",
                            e.target.value ? Number(e.target.value) : null,
                          )
                        }
                        className="h-7 text-xs"
                      />
                      {suggestedFields.has(`item-${idx}-minutes`) ? (
                        <Badge
                          variant="secondary"
                          className="bg-purple-100 text-purple-700 text-[9px] px-1 py-0 h-4 dark:bg-purple-900/50 dark:text-purple-300"
                        >
                          suggested
                        </Badge>
                      ) : null}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* ACTION ITEMS FORM */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Action Items (Follow-ups)
              </h4>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1 text-xs text-purple-600 hover:text-purple-700"
                onClick={addActionItem}
              >
                <Plus className="size-3.5" /> Add Action
              </Button>
            </div>

            {actionItems.length === 0 ? (
              <p className="text-xs text-muted-foreground italic">No action items defined.</p>
            ) : null}

            {actionItems.map((act, idx) => (
              <div
                key={idx}
                className="space-y-2 rounded-lg border bg-background p-3 text-xs"
              >
                <div className="flex items-center gap-2">
                  <Input
                    placeholder="Task to do *"
                    value={act.task}
                    onChange={(e) => handleActionItemChange(idx, "task", e.target.value)}
                    className="h-8 text-xs font-medium flex-1"
                  />
                  {suggestedFields.has(`action-${idx}-task`) ? (
                    <Badge
                      variant="secondary"
                      className="bg-purple-100 text-purple-700 text-[10px] px-1.5 py-0 h-5 dark:bg-purple-900/50 dark:text-purple-300"
                    >
                      suggested
                    </Badge>
                  ) : null}
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-8 text-muted-foreground hover:text-destructive"
                    onClick={() => removeActionItem(idx)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="flex items-center gap-1">
                    <Input
                      placeholder="Assignee / Owner"
                      value={act.owner ?? ""}
                      onChange={(e) => handleActionItemChange(idx, "owner", e.target.value)}
                      className="h-7 text-xs"
                    />
                    {suggestedFields.has(`action-${idx}-owner`) ? (
                      <Badge
                        variant="secondary"
                        className="bg-purple-100 text-purple-700 text-[9px] px-1 py-0 h-4 dark:bg-purple-900/50 dark:text-purple-300"
                      >
                        suggested
                      </Badge>
                    ) : null}
                  </div>

                  <div className="flex items-center gap-1">
                    <Input
                      type="date"
                      value={act.due ?? ""}
                      onChange={(e) =>
                        handleActionItemChange(idx, "due", e.target.value || null)
                      }
                      className="h-7 text-xs"
                    />
                    {suggestedFields.has(`action-${idx}-due`) ? (
                      <Badge
                        variant="secondary"
                        className="bg-purple-100 text-purple-700 text-[9px] px-1 py-0 h-4 dark:bg-purple-900/50 dark:text-purple-300"
                      >
                        suggested
                      </Badge>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* ACTION BUTTONS */}
          <div className="flex items-center justify-end gap-2 pt-2">
            {meeting.agenda ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => setIsEditing(false)}
                disabled={isSaving}
              >
                Cancel
              </Button>
            ) : null}

            <Button
              type="button"
              size="sm"
              className="bg-primary text-primary-foreground text-xs"
              onClick={handleSave}
              disabled={isSaving || items.every((i) => !i.topic.trim())}
            >
              {isSaving ? <Loader2 className="size-3.5 animate-spin mr-1.5" /> : null}
              Save Agenda
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  )
}
