export type Product = {
  id: number | string
  name?: string
  keywords: string[]
  max_price: number
  min_price?: number | null
  exclude_terms?: string[]
  merchants?: string[]
  category?: string
  auto_approve?: boolean
  active?: boolean
  created_by?: string
  created_at?: string
}

export type ProductPayload = Omit<Product, 'id'>

export type Finding = {
  id: number | string
  timestamp: string
  product_keyword: string
  url: string
  price_found: number | null
  price_ok: boolean
  source_group: string
  coupons: string[]
  links: string[]
  source_chat_id?: string
  source_message_id?: string
  product_title?: string
  merchant?: string
  message_type?: string
  match_reason?: string
  confidence?: number | null
  raw_message?: string
  message_hash?: string
  url_hash?: string
  decision?: 'approved' | 'review' | 'rejected' | string
  matched_rule_id?: string
  rule_name?: string
  detected_title?: string
  price_source?: string
  reason_codes?: string[]
  score_breakdown?: Record<string, number>
  schema_version?: number
  user_id?: string
}

export type MessageEventStats = {
  source_group: string
  decision: string
  message_type: string
  total: number
  avg_confidence: number | null
  with_price: number
  with_links: number
  with_coupons: number
  first_seen: string
  last_seen: string
}

export type ApiState = {
  products: Product[]
  findings: Finding[]
}

export type FindingsPage = {
  findings: Finding[]
  limit: number
  offset: number
}
