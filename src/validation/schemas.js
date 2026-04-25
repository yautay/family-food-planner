import { z } from 'zod'

const dateRegex = /^\d{4}-\d{2}-\d{2}$/

const positiveInt = z.coerce.number().int().positive()
const trimmedString = z.string().trim()

const optionalText = z
  .union([z.string(), z.null(), z.undefined()])
  .transform((value) => (typeof value === 'string' ? value.trim() : ''))

const optionalPositiveNumber = z
  .union([z.number(), z.string(), z.null(), z.undefined()])
  .transform((value) => {
    if (value === '' || value === null || value === undefined) {
      return undefined
    }

    const parsed = Number(value)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined
  })

const optionalFiniteNumber = z
  .union([z.number(), z.string(), z.null(), z.undefined()])
  .transform((value) => {
    if (value === '' || value === null || value === undefined) {
      return undefined
    }

    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : undefined
  })

const idParams = z.object({
  id: positiveInt,
})

const idItemParams = z.object({
  id: positiveInt,
  itemId: positiveInt,
})

const mealPlanDateParams = z.object({
  id: positiveInt,
  plannedDate: z.string().regex(dateRegex, 'plannedDate must use YYYY-MM-DD format'),
})

const mealPlanIdParams = z.object({
  mealPlanId: positiveInt,
})

const searchQuery = z
  .object({
    search: z
      .union([z.string(), z.undefined()])
      .transform((value) => (typeof value === 'string' ? value.trim().slice(0, 120) : undefined)),
  })
  .passthrough()

const auditQuery = z
  .object({
    limit: z.union([z.string(), z.number(), z.undefined()]).transform((value) => {
      if (value === undefined || value === '') {
        return undefined
      }
      const parsed = Number(value)
      return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined
    }),
  })
  .passthrough()

const registerBody = z
  .object({
    username: trimmedString.min(3).max(60),
    email: trimmedString.email().max(254),
    password: z.string().min(8).max(128),
    captcha_token: trimmedString.min(1).max(2048).optional(),
  })
  .passthrough()

const loginBody = z
  .object({
    identity: trimmedString.min(1).max(254),
    password: z.string().min(1).max(128),
  })
  .passthrough()

const changePasswordBody = z
  .object({
    currentPassword: z.string().min(1).max(128),
    newPassword: z.string().min(8).max(128),
  })
  .passthrough()

const forgotPasswordBody = z
  .object({
    email: trimmedString.email().max(254),
    captcha_token: trimmedString.min(1).max(2048).optional(),
  })
  .passthrough()

const resetPasswordBody = z
  .object({
    token: trimmedString.min(1).max(2048),
    newPassword: z.string().min(8).max(128),
  })
  .passthrough()

const roleUpdateBody = z
  .object({
    roles: z.array(trimmedString.min(1).max(80)).max(20),
  })
  .passthrough()

const permissionUpdateBody = z
  .object({
    permissions: z
      .array(
        z.union([
          trimmedString.min(1).max(80),
          z
            .object({
              name: trimmedString.min(1).max(80),
              allow: z.union([z.boolean(), z.undefined()]).optional(),
            })
            .passthrough(),
        ]),
      )
      .max(100),
  })
  .passthrough()

const nameBody = z
  .object({
    name: trimmedString.min(1).max(120),
  })
  .passthrough()

const ingredientBody = z
  .object({
    name: trimmedString.min(1).max(200),
    comment: optionalText,
    unit_id: positiveInt,
    unit_to_ml: optionalPositiveNumber,
    packageTypeId: z.union([positiveInt, z.undefined(), z.null()]).optional(),
    quantityPerPackage: optionalPositiveNumber,
    calories: optionalFiniteNumber,
    carbohydrates: optionalFiniteNumber,
    sugars: optionalFiniteNumber,
    fat: optionalFiniteNumber,
    protein: optionalFiniteNumber,
    fiber: optionalFiniteNumber,
    tag_id: z.array(positiveInt).optional(),
  })
  .passthrough()

const packageBody = z
  .object({
    product_id: positiveInt,
    package_type_id: z.union([positiveInt, z.undefined(), z.null()]).optional(),
    package_type_name: z.union([trimmedString.min(1).max(120), z.undefined(), z.null()]).optional(),
    grams_per_package: z.coerce.number().positive(),
    source: z.union([trimmedString.max(120), z.undefined(), z.null()]).optional(),
  })
  .passthrough()

const recipeIngredientSchema = z
  .object({
    product_id: z.union([positiveInt, z.undefined(), z.null()]).optional(),
    product_name: z.union([trimmedString.min(1).max(200), z.undefined(), z.null()]).optional(),
    quantity: optionalFiniteNumber,
    unit_id: z.union([positiveInt, z.undefined(), z.null()]).optional(),
    unit_name: z.union([trimmedString.min(1).max(120), z.undefined(), z.null()]).optional(),
    grams: optionalFiniteNumber,
    note: optionalText,
  })
  .passthrough()

const recipeBody = z
  .object({
    name: trimmedString.min(1).max(200),
    instructions: z.union([z.string(), z.undefined(), z.null()]).optional(),
    ingredients: z.array(recipeIngredientSchema).max(500),
  })
  .passthrough()

const mealEntrySchema = z
  .object({
    planned_date: z.string().regex(dateRegex, 'planned_date must use YYYY-MM-DD format'),
    meal_slot: trimmedString.min(1).max(40),
    recipe_id: z.union([positiveInt, z.undefined(), z.null()]).optional(),
    custom_name: z.union([trimmedString.min(1).max(200), z.undefined(), z.null()]).optional(),
    servings: optionalPositiveNumber,
    note: optionalText,
  })
  .passthrough()

const mealSlotSchema = z
  .object({
    slot_name: trimmedString.min(1).max(80),
    slot_time: z
      .union([z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/), z.null(), z.undefined()])
      .optional(),
  })
  .passthrough()

const mealItemSchema = z
  .object({
    recipe_id: positiveInt,
    servings: optionalPositiveNumber,
    portions: optionalPositiveNumber,
    note: optionalText,
  })
  .passthrough()

const mealPlanBody = z
  .object({
    name: trimmedString.min(1).max(120),
    start_date: z.string().regex(dateRegex, 'start_date must use YYYY-MM-DD format'),
    end_date: z.string().regex(dateRegex, 'end_date must use YYYY-MM-DD format'),
    note: optionalText,
    portions_count: z.union([positiveInt, z.undefined()]).optional(),
  })
  .passthrough()

const daySlotBody = z
  .object({
    day_plan_id: z.union([positiveInt, z.null(), z.undefined()]).optional(),
    note: optionalText,
  })
  .passthrough()

const dayPlanBody = z
  .object({
    name: trimmedString.min(1).max(120),
    note: optionalText,
  })
  .passthrough()

const dayMealsBody = z
  .object({
    meals: z.array(mealItemSchema).max(20),
  })
  .passthrough()

const mealEntriesBody = z
  .object({
    entries: z.array(mealEntrySchema).max(400),
  })
  .passthrough()

const mealSlotsBody = z
  .object({
    slots: z.array(mealSlotSchema).min(1).max(20),
  })
  .passthrough()

const daySlotMealsBody = z
  .object({
    meals: z.array(mealItemSchema).max(20),
  })
  .passthrough()

const shoppingListBody = z
  .object({
    name: trimmedString.min(1).max(120),
    status: z.union([z.literal('open'), z.literal('archived'), z.undefined()]).optional(),
    note: optionalText,
    meal_plan_id: z.union([positiveInt, z.null(), z.undefined()]).optional(),
  })
  .passthrough()

const shoppingListItemBody = z
  .object({
    product_id: z.union([positiveInt, z.null(), z.undefined()]).optional(),
    custom_name: z.union([trimmedString.min(1).max(200), z.null(), z.undefined()]).optional(),
    quantity: optionalFiniteNumber,
    unit_id: z.union([positiveInt, z.null(), z.undefined()]).optional(),
    note: optionalText,
    is_checked: z.union([z.boolean(), z.number(), z.string(), z.undefined()]).optional(),
  })
  .passthrough()

const generateShoppingBody = z
  .object({
    name: z.union([trimmedString.min(1).max(120), z.undefined(), z.null()]).optional(),
    note: optionalText,
  })
  .passthrough()

export const schemas = {
  idParams,
  idItemParams,
  mealPlanDateParams,
  mealPlanIdParams,
  searchQuery,
  auditQuery,
  registerBody,
  loginBody,
  changePasswordBody,
  forgotPasswordBody,
  resetPasswordBody,
  roleUpdateBody,
  permissionUpdateBody,
  nameBody,
  ingredientBody,
  packageBody,
  recipeBody,
  mealPlanBody,
  daySlotBody,
  dayPlanBody,
  dayMealsBody,
  mealEntriesBody,
  mealSlotsBody,
  daySlotMealsBody,
  shoppingListBody,
  shoppingListItemBody,
  generateShoppingBody,
}

export default schemas
