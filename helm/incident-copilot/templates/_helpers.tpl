{{/*
Expand the name of the chart.
*/}}
{{- define "incident-copilot.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "incident-copilot.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "incident-copilot.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "incident-copilot.labels" -}}
helm.sh/chart: {{ include "incident-copilot.chart" . }}
{{ include "incident-copilot.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "incident-copilot.selectorLabels" -}}
app.kubernetes.io/name: {{ include "incident-copilot.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "incident-copilot.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "incident-copilot.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Redis fullname
*/}}
{{- define "incident-copilot.redis.fullname" -}}
{{- printf "%s-redis" (include "incident-copilot.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Redis URL
*/}}
{{- define "incident-copilot.redisUrl" -}}
{{- if .Values.redis.enabled }}
{{- printf "redis://%s:%d" (include "incident-copilot.redis.fullname" .) (int .Values.redis.service.port) }}
{{- else }}
{{- .Values.redis.externalUrl }}
{{- end }}
{{- end }}
