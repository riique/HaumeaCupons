import {
  addDoc,
  collection,
  deleteDoc,
  doc,
  getDocs,
  limit,
  orderBy,
  query,
  serverTimestamp,
  setDoc,
  updateDoc,
  writeBatch,
  type DocumentData,
  type QueryDocumentSnapshot,
} from 'firebase/firestore'

import { auth, db } from './firebase'
import type { ApiState, Finding, Product, ProductPayload } from './types'

function requireDb() {
  if (!db) throw new Error('Firestore não configurado.')
  return db
}

function timestampToIso(value: unknown): string {
  if (!value) return ''
  if (typeof value === 'string') return value
  if (value instanceof Date) return value.toISOString()
  if (typeof value === 'object' && 'toDate' in value && typeof value.toDate === 'function') {
    return value.toDate().toISOString()
  }
  return String(value)
}

function productFromDoc(docSnap: QueryDocumentSnapshot<DocumentData>, fallbackIndex: number): Product {
  const data = docSnap.data()
  return {
    id: data.id ?? docSnap.id,
    keywords: Array.isArray(data.keywords) ? data.keywords.map(String) : [],
    max_price: Number(data.maxPrice ?? data.max_price ?? 0),
    active: data.active ?? true,
    created_by: String(data.createdBy ?? data.created_by ?? ''),
    created_at: timestampToIso(data.createdAt ?? data.created_at) || String(fallbackIndex),
  }
}

function findingFromDoc(docSnap: QueryDocumentSnapshot<DocumentData>): Finding {
  const data = docSnap.data()
  return {
    id: docSnap.id,
    timestamp: timestampToIso(data.timestamp ?? data.createdAt),
    product_keyword: String(data.productKeyword ?? data.product_keyword ?? ''),
    url: String(data.url ?? ''),
    price_found: data.priceFound ?? data.price_found ?? null,
    price_ok: Boolean(data.priceOk ?? data.price_ok ?? false),
    source_group: String(data.sourceGroup ?? data.source_group ?? ''),
    coupons: Array.isArray(data.coupons) ? data.coupons.map(String) : [],
    links: Array.isArray(data.links) ? data.links.map(String) : [],
    source_chat_id: String(data.sourceChatId ?? data.source_chat_id ?? ''),
    source_message_id: String(data.sourceMessageId ?? data.source_message_id ?? ''),
    raw_message: String(data.rawMessage ?? data.raw_message ?? ''),
    user_id: String(data.userId ?? data.user_id ?? ''),
  }
}

export async function fetchProducts(): Promise<Product[]> {
  const database = requireDb()
  const docs = await getDocs(query(collection(database, 'products'), orderBy('createdAt', 'asc')))
  return docs.docs.map(productFromDoc).filter((product) => product.active !== false)
}

export async function addProduct(product: ProductPayload): Promise<string> {
  const database = requireDb()
  const ref = await addDoc(collection(database, 'products'), {
    keywords: product.keywords,
    maxPrice: product.max_price,
    active: product.active ?? true,
    createdBy: auth?.currentUser?.email ?? auth?.currentUser?.uid ?? 'dashboard',
    createdAt: serverTimestamp(),
    updatedAt: serverTimestamp(),
  })
  await updateDoc(ref, { id: ref.id })
  return ref.id
}

export async function updateProduct(id: string | number, product: ProductPayload): Promise<void> {
  const database = requireDb()
  await setDoc(
    doc(database, 'products', String(id)),
    {
      id,
      keywords: product.keywords,
      maxPrice: product.max_price,
      active: product.active ?? true,
      updatedAt: serverTimestamp(),
    },
    { merge: true },
  )
}

export async function deleteProduct(id: string | number): Promise<void> {
  const database = requireDb()
  await deleteDoc(doc(database, 'products', String(id)))
}

export async function fetchFindings(limitCount = 200): Promise<Finding[]> {
  const database = requireDb()
  const docs = await getDocs(query(collection(database, 'findings'), orderBy('timestamp', 'desc'), limit(limitCount)))
  return docs.docs.map(findingFromDoc)
}

export async function deleteFinding(id: string | number): Promise<void> {
  const database = requireDb()
  await deleteDoc(doc(database, 'findings', String(id)))
}

export async function clearAllFindings(): Promise<void> {
  const database = requireDb()
  while (true) {
    const docs = await getDocs(query(collection(database, 'findings'), limit(500)))
    if (docs.empty) return
    const batch = writeBatch(database)
    docs.docs.forEach((docSnap) => batch.delete(docSnap.ref))
    await batch.commit()
  }
}

export async function fetchDashboardState(): Promise<ApiState> {
  const [products, findings] = await Promise.all([
    fetchProducts(),
    fetchFindings(200),
  ])
  return {
    products,
    findings,
  }
}
