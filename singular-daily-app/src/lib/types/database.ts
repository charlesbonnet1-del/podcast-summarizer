export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export interface Database {
  public: {
    Tables: {
      users: {
        Row: {
          id: string
          email: string
          first_name: string | null
          last_name: string | null
          target_duration: number
          include_international: boolean
          settings: Json | null
          rss_token: string
          subscription_status: 'free' | 'pro'
          created_at: string
          updated_at: string
        }
        Insert: {
          id: string
          email: string
          first_name?: string | null
          last_name?: string | null
          target_duration?: number
          include_international?: boolean
          settings?: Json | null
          rss_token?: string
          subscription_status?: 'free' | 'pro'
          created_at?: string
          updated_at?: string
        }
        Update: {
          id?: string
          email?: string
          first_name?: string | null
          last_name?: string | null
          target_duration?: number
          include_international?: boolean
          settings?: Json | null
          rss_token?: string
          subscription_status?: 'free' | 'pro'
          created_at?: string
          updated_at?: string
        }
      }
      content_queue: {
        Row: {
          id: string
          user_id: string
          url: string
          title: string | null
          source_type: 'youtube' | 'article' | 'podcast'
          source: string | null
          source_country: string
          priority: 'high' | 'normal'
          keyword: string | null
          edition: string | null
          status: 'pending' | 'processing' | 'processed' | 'failed'
          error_message: string | null
          processed_content: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          user_id: string
          url: string
          title?: string | null
          source_type: 'youtube' | 'article' | 'podcast'
          source?: string | null
          source_country?: string
          priority?: 'high' | 'normal'
          keyword?: string | null
          edition?: string | null
          status?: 'pending' | 'processing' | 'processed' | 'failed'
          error_message?: string | null
          processed_content?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          id?: string
          user_id?: string
          url?: string
          title?: string | null
          source_type?: 'youtube' | 'article' | 'podcast'
          source?: string | null
          source_country?: string
          priority?: 'high' | 'normal'
          keyword?: string | null
          edition?: string | null
          status?: 'pending' | 'processing' | 'processed' | 'failed'
          error_message?: string | null
          processed_content?: string | null
          created_at?: string
          updated_at?: string
        }
      }
      episodes: {
        Row: {
          id: string
          user_id: string
          title: string
          summary_text: string | null
          audio_url: string
          audio_duration: number | null
          sources_data: Json
          created_at: string
        }
        Insert: {
          id?: string
          user_id: string
          title: string
          summary_text?: string | null
          audio_url: string
          audio_duration?: number | null
          sources_data?: Json
          created_at?: string
        }
        Update: {
          id?: string
          user_id?: string
          title?: string
          summary_text?: string | null
          audio_url?: string
          audio_duration?: number | null
          sources_data?: Json
          created_at?: string
        }
      }
      cached_intros: {
        Row: {
          id: string
          first_name_normalized: string
          audio_url: string
          audio_duration: number
          created_at: string
          updated_at: string
        }
      }
      daily_ephemeride: {
        Row: {
          id: string
          date: string
          script: string
          audio_url: string | null
          audio_duration: number
          saint_of_day: string | null
          historical_fact: string | null
          created_at: string
        }
      }
      processed_segments: {
        Row: {
          id: string
          url: string
          date: string
          segment_type: string
          title: string | null
          script: string | null
          audio_url: string | null
          audio_duration: number
          word_count: number
          source_name: string | null
          source_country: string
          created_at: string
        }
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      [_ in never]: never
    }
  }
}

export type User = Database['public']['Tables']['users']['Row']
export type ContentQueue = Database['public']['Tables']['content_queue']['Row']
export type Episode = Database['public']['Tables']['episodes']['Row']

export interface UserInterest {
  id: string
  user_id: string
  keyword: string
  created_at: string
}
