import { literal } from 'sequelize'
import models from '../models/index.js'

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

  return models.auditLog.create({
    actor_user_id: actorUserId,
    action,
    target_type: targetType,
    target_id: targetId === null || targetId === undefined ? null : String(targetId),
    meta_json: JSON.stringify(meta ?? {}),
  })
}

async function listAuditLogs({ limit = 100 } = {}) {
  const normalizedLimit = normalizeLimit(limit)

  const rows = await models.auditLog.findAll({
    attributes: [
      'id',
      'actor_user_id',
      [literal('actor.username'), 'actor_username'],
      'action',
      'target_type',
      'target_id',
      'meta_json',
      'created_at',
    ],
    include: [
      {
        model: models.user,
        as: 'actor',
        attributes: [],
        required: false,
      },
    ],
    order: [['id', 'DESC']],
    limit: normalizedLimit,
    raw: true,
  })

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
