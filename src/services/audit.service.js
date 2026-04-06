import catalogDb from '../db/catalog.js'

function normalizeLimit(limit) {
  const parsed = Number(limit)
  if (!Number.isInteger(parsed) || parsed <= 0) {
    return 100
  }

  return Math.min(parsed, 500)
}

function logEvent({ actorUserId = null, action, targetType, targetId = null, meta = {} }) {
  if (!action || !targetType) {
    throw new Error('action and targetType are required for audit log event')
  }

  catalogDb
    .prepare(
      `
      INSERT INTO audit_logs(actor_user_id, action, target_type, target_id, meta_json)
      VALUES (?, ?, ?, ?, ?)
      `,
    )
    .run(
      actorUserId,
      action,
      targetType,
      targetId === null || targetId === undefined ? null : String(targetId),
      JSON.stringify(meta ?? {}),
    )
}

function listAuditLogs({ limit = 100 } = {}) {
  const normalizedLimit = normalizeLimit(limit)

  const rows = catalogDb
    .prepare(
      `
      SELECT
        a.id,
        a.actor_user_id,
        u.username AS actor_username,
        a.action,
        a.target_type,
        a.target_id,
        a.meta_json,
        a.created_at
      FROM audit_logs a
      LEFT JOIN users u ON u.id = a.actor_user_id
      ORDER BY a.id DESC
      LIMIT ?
      `,
    )
    .all(normalizedLimit)

  return rows.map((row) => {
    let meta = {}

    if (typeof row.meta_json === 'string' && row.meta_json.trim().length > 0) {
      try {
        meta = JSON.parse(row.meta_json)
      } catch (_error) {
        meta = { raw: row.meta_json }
      }
    }

    return {
      id: row.id,
      actor_user_id: row.actor_user_id,
      actor_username: row.actor_username,
      action: row.action,
      target_type: row.target_type,
      target_id: row.target_id,
      meta,
      created_at: row.created_at,
    }
  })
}

export default {
  logEvent,
  listAuditLogs,
}
