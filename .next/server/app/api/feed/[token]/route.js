"use strict";(()=>{var e={};e.id=262,e.ids=[262],e.modules={399:e=>{e.exports=require("next/dist/compiled/next-server/app-page.runtime.prod.js")},517:e=>{e.exports=require("next/dist/compiled/next-server/app-route.runtime.prod.js")},217:(e,t,r)=>{r.r(t),r.d(t,{originalPathname:()=>m,patchFetch:()=>f,requestAsyncStorage:()=>d,routeModule:()=>l,serverHooks:()=>g,staticGenerationAsyncStorage:()=>c});var i={};r.r(i),r.d(i,{GET:()=>p});var n=r(9303),s=r(8716),a=r(670),o=r(6596),u=r(7070);async function p(e,{params:t}){let r=process.env.NEXT_PUBLIC_SUPABASE_URL,i=process.env.SUPABASE_SERVICE_ROLE_KEY;if(!r||!i)return new u.NextResponse("Server configuration error",{status:500});let n=(0,o.eI)(r,i),{token:s}=await t,{data:a,error:p}=await n.from("users").select("id, email").eq("rss_token",s).single();if(p||!a)return new u.NextResponse("Feed not found",{status:404});let{data:l,error:d}=await n.from("episodes").select("*").eq("user_id",a.id).order("created_at",{ascending:!1}).limit(50);if(d)return new u.NextResponse("Error fetching episodes",{status:500});let c=process.env.NEXT_PUBLIC_APP_URL||"https://singular.daily",g=`${c}/api/feed/${s}`,m=function(e){let{title:t,description:r,feedUrl:i,siteUrl:n,episodes:s}=e,a=e=>e.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&apos;"),o=e=>new Date(e).toUTCString(),u=e=>e?`${Math.floor(e/3600).toString().padStart(2,"0")}:${Math.floor(e%3600/60).toString().padStart(2,"0")}:${(e%60).toString().padStart(2,"0")}`:"00:15:00",p=s.map(e=>`
    <item>
      <title>${a(e.title)}</title>
      <description><![CDATA[${e.summary_text||"Your daily audio digest"}]]></description>
      <pubDate>${o(e.created_at)}</pubDate>
      <enclosure url="${a(e.audio_url)}" type="audio/mpeg" length="0"/>
      <guid isPermaLink="false">${e.id}</guid>
      <itunes:duration>${u(e.audio_duration)}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>`).join("\n");return`<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" 
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:content="http://purl.org/rss/1.0/modules/content/"
  xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>${a(t)}</title>
    <description>${a(r)}</description>
    <link>${a(n)}</link>
    <atom:link href="${a(i)}" rel="self" type="application/rss+xml"/>
    <language>en-us</language>
    <itunes:author>Singular Daily</itunes:author>
    <itunes:summary>${a(r)}</itunes:summary>
    <itunes:type>episodic</itunes:type>
    <itunes:explicit>false</itunes:explicit>
    <itunes:category text="Technology"/>
    <itunes:image href="${n}/podcast-cover.png"/>
    ${p}
  </channel>
</rss>`}({title:`Singular Daily - ${a.email?.split("@")[0]}'s Digest`,description:"Your personalized AI-generated audio digest",feedUrl:g,siteUrl:c,episodes:l||[]});return new u.NextResponse(m,{headers:{"Content-Type":"application/rss+xml; charset=utf-8","Cache-Control":"public, max-age=300"}})}let l=new n.AppRouteRouteModule({definition:{kind:s.x.APP_ROUTE,page:"/api/feed/[token]/route",pathname:"/api/feed/[token]",filename:"route",bundlePath:"app/api/feed/[token]/route"},resolvedPagePath:"/workspaces/podcast-summarizer/src/app/api/feed/[token]/route.ts",nextConfigOutput:"",userland:i}),{requestAsyncStorage:d,staticGenerationAsyncStorage:c,serverHooks:g}=l,m="/api/feed/[token]/route";function f(){return(0,a.patchFetch)({serverHooks:g,staticGenerationAsyncStorage:c})}}};var t=require("../../../../webpack-runtime.js");t.C(e);var r=e=>t(t.s=e),i=t.X(0,[948,316,972],()=>r(217));module.exports=i})();